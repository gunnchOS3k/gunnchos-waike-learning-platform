"""Single-origin Linux deployment for the existing Hub and compiled public reader.

Run exactly one ASGI worker: SQLite and rate limits are process-local. TLS and a
trusted host allowlist belong to the existing HTTPS ingress, never a dev server.
"""
from __future__ import annotations

from collections import OrderedDict, deque
from contextlib import asynccontextmanager
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

MAX_BODY = 2 * 1024 * 1024
MAX_RATE_KEYS = 4096


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if '.git' in path.parts or '__pycache__' in path.parts or not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError('RELEASE_SYMLINK_FORBIDDEN')
        digest.update(path.relative_to(root).as_posix().encode() + b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def settings() -> dict:
    if os.environ.get('WAIKE_ENV') != 'production':
        raise ValueError('PRODUCTION_ENV_REQUIRED')
    for name in ('WAIKE_FIXTURE_AUTH', 'WAIKE_SEED_TEST_FIXTURES', 'WAIKE_PIXEL_PILOT', 'WAIKE_ALLOW_FAKE_AI'):
        if os.environ.get(name, '').lower() in {'true', '1', 'yes'}:
            raise ValueError('PRODUCTION_TEST_FLAGS_FORBIDDEN')
    origin = os.environ.get('WAIKE_PUBLIC_ORIGIN', '')
    url = urlsplit(origin)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.path not in ('', '/') or url.query or url.fragment:
        raise ValueError('EXACT_HTTPS_PUBLIC_ORIGIN_REQUIRED')
    secret = os.environ.get('WAIKE_PRACTICE_SIGNING_KEY', '')
    if not secret:
        secret_path = Path(os.environ['WAIKE_PRACTICE_SIGNING_KEY_FILE'])
        secret = secret_path.read_text().strip()
    if len(secret) < 32 or len(secret) > 512:
        raise ValueError('PRACTICE_SIGNING_KEY_REQUIRED')
    os.environ['WAIKE_PRACTICE_SIGNING_KEY'] = secret
    source = Path(os.environ['WAIKE_ROOT']).resolve()
    static = Path(os.environ['WAIKE_STATIC_ROOT']).resolve()
    db = Path(os.environ['WAIKE_HUB_DB'])
    if not db.is_absolute() or not db.parent.is_dir():
        raise ValueError('EXPLICIT_PERSISTENT_DB_DIRECTORY_REQUIRED')
    manifest = json.loads(Path(os.environ['WAIKE_RELEASE_MANIFEST']).read_text())
    pin = json.loads((Path(__file__).resolve().parents[3] / 'curriculum/registry/PIN.json').read_text())
    if manifest['curriculum_commit'] != pin['pinned_commit']:
        raise ValueError('CURRICULUM_PIN_MISMATCH')
    if tree_hash(source) != manifest['curriculum_tree_sha256'] or tree_hash(static) != manifest['reader_tree_sha256']:
        raise ValueError('RELEASE_TREE_MISMATCH')
    if not (static / 'index.html').is_file():
        raise ValueError('READER_BUILD_REQUIRED')
    from app.db import MIGRATIONS
    import sqlite3
    if not db.is_file():
        raise ValueError('DATABASE_REQUIRES_EXPLICIT_MIGRATION')
    probe = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    try:
        versions = [r[0] for r in probe.execute('SELECT version FROM schema_migrations ORDER BY version')]
        if versions != [v for v, _ in MIGRATIONS]:
            raise ValueError('DATABASE_REQUIRES_EXPLICIT_MIGRATION')
    finally:
        probe.close()
    return dict(origin=origin.rstrip('/'), host=url.hostname, static=static, manifest=manifest)


class ProductionBoundary:
    """Bound total request bytes before parsing; no bearer tokens or body in logs.

    Exact Origin enforcement complements existing bearer authorization. Limits
    use the actual TCP peer; forwarded headers are not trusted by this process.
    The ingress must additionally apply distributed limits to real client IPs.
    """
    def __init__(self, app, origin: str, limit: int = 120):
        self.app, self.origin, self.limit = app, origin, limit
        self.buckets: OrderedDict[tuple, deque] = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        path = scope['path']
        async def reply(code, detail):
            response = JSONResponse({'detail': detail}, code, headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', **({'Retry-After': '60'} if code == 429 else {})})
            await response(scope, receive, send)
        if path in {'/docs', '/redoc', '/openapi.json', '/config', '/version'}:
            return await reply(404, 'Not found')
        if path.startswith('/api/'):
            origin = headers.get(b'origin', b'').decode('latin1')
            if origin and origin != self.origin:
                return await reply(403, 'ORIGIN_FORBIDDEN')
            key = (scope.get('client', ('unknown',))[0], 'login' if path == '/api/v1/auth/login' else 'api')
            now = time.monotonic()
            hits = self.buckets.pop(key, deque())
            while hits and hits[0] <= now - 60:
                hits.popleft()
            self.buckets[key] = hits
            while len(self.buckets) > MAX_RATE_KEYS:
                self.buckets.popitem(last=False)
            if len(hits) >= (10 if key[1] == 'login' else self.limit):
                return await reply(429, 'RATE_LIMITED')
            hits.append(now)
            try:
                length = int(headers.get(b'content-length', b'0'))
                if length < 0:
                    return await reply(400, 'INVALID_CONTENT_LENGTH')
                if length > MAX_BODY:
                    return await reply(413, 'REQUEST_TOO_LARGE')
            except ValueError:
                return await reply(400, 'INVALID_CONTENT_LENGTH')
            chunks, size = [], 0
            deadline = time.monotonic() + 15
            while True:
                try:
                    message = await asyncio.wait_for(receive(), timeout=max(0.001, deadline - time.monotonic()))
                except TimeoutError:
                    return await reply(408, 'REQUEST_TIMEOUT')
                if message['type'] == 'http.disconnect':
                    return
                size += len(message.get('body', b''))
                if size > MAX_BODY:
                    return await reply(413, 'REQUEST_TOO_LARGE')
                chunks.append(message.get('body', b''))
                if not message.get('more_body'):
                    break
            delivered = False
            async def buffered_receive():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {'type': 'http.request', 'body': b''.join(chunks), 'more_body': False}
            source_receive = buffered_receive
        else:
            source_receive = receive
        async def secured_send(message):
            if message['type'] == 'http.response.start':
                extra = [(b'x-content-type-options', b'nosniff'), (b'referrer-policy', b'no-referrer'), (b'permissions-policy', b'camera=(), microphone=(), geolocation=()'), (b'x-frame-options', b'DENY'), (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")]
                message['headers'] = list(message.get('headers', [])) + extra
                if path.startswith('/api/'):
                    message['headers'] = [(k,v) for k,v in message['headers'] if k.lower() != b'cache-control'] + [(b'cache-control', b'no-store')]
            await send(message)
        await self.app(scope, source_receive, secured_send)


def create_production_app():
    config = settings()
    # Factory mode prevents app.main from opening a second unserved database.
    os.environ['WAIKE_FACTORY_MODE'] = 'true'
    from app.main import HubConfig, create_app
    lock = (Path(os.environ['WAIKE_HUB_DB']).parent / '.hub.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock.close()
        raise ValueError('HUB_OR_MAINTENANCE_ALREADY_RUNNING') from exc
    try:
        app = create_app(config=HubConfig(environment='production'), db_path=Path(os.environ['WAIKE_HUB_DB']))
    except Exception:
        lock.close()
        raise
    app.state.maintenance_lock = lock
    previous_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            try:
                yield
            finally:
                app.state.db.close()
                lock.close()
    app.router.lifespan_context = lifespan
    # Same-origin browser deployment does not need Tauri/opaque-origin CORS.
    app.user_middleware = [m for m in app.user_middleware if m.cls.__name__ != 'CORSMiddleware']

    @app.get('/readyz')
    def ready():
        app.state.db.execute('SELECT 1').fetchone()
        return {'status': 'ready', 'curriculum_commit': config['manifest']['curriculum_commit'], 'platform_commit': config['manifest']['platform_commit'], 'seeded_test_fixtures': False}

    @app.get('/{requested:path}', include_in_schema=False)
    def reader(requested: str):
        # Explicit assets only: never SPA-fallback a private/API or missing path.
        candidate = (config['static'] / (requested or 'index.html')).resolve()
        if requested.startswith(('api/', '.')) or not candidate.is_relative_to(config['static']) or not candidate.is_file():
            raise HTTPException(404, 'Not found')
        if candidate.suffix not in {'.html', '.js', '.css', '.png', '.svg', '.ico', '.webmanifest', '.woff2', '.json'}:
            raise HTTPException(404, 'Not found')
        return FileResponse(candidate, headers={'Cache-Control': 'public, max-age=31536000, immutable' if requested.startswith('assets/') else 'no-cache'})

    app.add_middleware(ProductionBoundary, origin=config['origin'])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[config['host'], 'localhost'])
    return app
