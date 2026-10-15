"""Production boundary and operator recovery checks with synthetic local records only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import zipfile

from fastapi.testclient import TestClient
import pytest

from app.db import connect, migrate, MIGRATIONS
from app.main import create_app, HubConfig
from app.production import create_production_app, settings, tree_hash, MAX_BODY, ProductionBoundary

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('host_operations', ROOT / 'deploy/production/operations.py')
ops = importlib.util.module_from_spec(spec); spec.loader.exec_module(ops)


@pytest.fixture
def release(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'canonical.json').write_text('{"test_fixture":true}')
    static = tmp_path / 'reader'; static.mkdir()
    (static / 'assets').mkdir()
    (static / 'index.html').write_text('<!doctype html><title>Isolated test reader</title>')
    (static / 'assets/test.js').write_text('console.log("synthetic fixture");')
    data = tmp_path / 'data'; data.mkdir()
    conn = connect(data / 'hub.sqlite3'); migrate(conn); conn.close()
    manifest = tmp_path / 'release.json'
    pin = json.loads((ROOT / 'curriculum/registry/PIN.json').read_text())['pinned_commit']
    manifest.write_text(json.dumps(dict(curriculum_commit=pin, platform_commit='synthetic-test', curriculum_tree_sha256=tree_hash(source), reader_tree_sha256=tree_hash(static))))
    for name in ('WAIKE_SEED_TEST_FIXTURES', 'WAIKE_FIXTURE_AUTH', 'WAIKE_PIXEL_PILOT', 'WAIKE_ALLOW_FAKE_AI'):
        monkeypatch.delenv(name, raising=False)
    for name,value in dict(WAIKE_ENV='production', WAIKE_ROOT=str(source), WAIKE_STATIC_ROOT=str(static), WAIKE_HUB_DB=str(data/'hub.sqlite3'), WAIKE_RELEASE_MANIFEST=str(manifest), WAIKE_PUBLIC_ORIGIN='https://learn.example.org', WAIKE_PRACTICE_SIGNING_KEY='x'*64).items():
        monkeypatch.setenv(name, value)
    return dict(source=source, static=static, data=data, manifest=manifest)


@pytest.mark.parametrize('name', ['WAIKE_FIXTURE_AUTH', 'WAIKE_SEED_TEST_FIXTURES', 'WAIKE_PIXEL_PILOT', 'WAIKE_ALLOW_FAKE_AI'])
def test_production_rejects_fixture_and_pilot_startup(release, monkeypatch, name):
    monkeypatch.setenv(name, 'true')
    with pytest.raises(ValueError, match='PRODUCTION_TEST_FLAGS_FORBIDDEN'): settings()


@pytest.mark.parametrize('config,seed', [(HubConfig(environment='production', fixture_auth_enabled=True),False), (HubConfig(environment='production'),True), (HubConfig(environment='production',production_auth_enabled=False),False)])
def test_direct_hub_also_rejects_unsafe_production(release, config, seed):
    with pytest.raises(ValueError, match='PRODUCTION_'):
        create_app(config=config, db_path=release['data']/'unsafe.sqlite3', seed=seed)
    assert not (release['data']/'unsafe.sqlite3').exists()


def test_production_source_pin_and_bytes_fail_closed(release):
    record = json.loads(release['manifest'].read_text()); record['curriculum_commit'] = '0'*40
    release['manifest'].write_text(json.dumps(record))
    with pytest.raises(ValueError, match='CURRICULUM_PIN_MISMATCH'): settings()


@pytest.mark.parametrize('key', ['source', 'static'])
def test_source_or_reader_tamper_fails(release, key):
    (release[key]/'tampered.json').write_text('{}')
    with pytest.raises(ValueError, match='RELEASE_TREE_MISMATCH'): settings()


def test_unsigned_http_origin_and_short_secret_rejected(release, monkeypatch):
    monkeypatch.setenv('WAIKE_PUBLIC_ORIGIN','http://learn.example.org')
    with pytest.raises(ValueError, match='HTTPS_PUBLIC_ORIGIN'): settings()
    monkeypatch.setenv('WAIKE_PUBLIC_ORIGIN','https://learn.example.org')
    monkeypatch.setenv('WAIKE_PRACTICE_SIGNING_KEY','short')
    with pytest.raises(ValueError, match='SIGNING_KEY'): settings()


def test_missing_unmigrated_database_fails(release):
    (release['data']/'hub.sqlite3').unlink()
    with pytest.raises(ValueError, match='EXPLICIT_MIGRATION'): settings()


def test_single_origin_reader_private_boundary_and_headers(release):
    with TestClient(create_production_app(), base_url='https://learn.example.org') as client:
        page = client.get('/')
        assert page.status_code == 200 and 'Isolated test reader' in page.text
        assert "script-src 'self'" in page.headers['content-security-policy']
        assert page.headers['x-frame-options'] == 'DENY'
        assert client.get('/assets/test.js').headers['cache-control'].endswith('immutable')
        for path in ('/docs','/openapi.json','/config','/version','/curriculum/instructor/answer_keys.json','/blobs/private','/api/v1/not-a-route'):
            assert client.get(path).status_code == 404
        denied = client.get('/api/v1/assignments')
        assert denied.status_code == 401 and denied.headers['cache-control'] == 'no-store'
        assert client.get('/api/v1/assignments',headers={'Origin':'https://hostile.example'}).status_code == 403
        assert client.get('/api/v1/assignments',headers={'X-Waike-Actor-Id':'learner-a','X-Waike-Actor-Role':'learner'}).status_code == 401
        assert client.post('/api/v1/auth/login',content='x',headers={'Content-Length':str(MAX_BODY+1)}).status_code == 413
        assert client.post('/api/v1/auth/login',content=b'x'*(MAX_BODY+1)).status_code == 413
        assert client.get('/',headers={'Host':'hostile.example'}).status_code == 400
        ready=client.get('/readyz').json()
        assert ready['seeded_test_fixtures'] is False
        assert client.app.state.db.execute('SELECT count(*) FROM users').fetchone()[0] == 0
        with pytest.raises(ValueError, match='HUB_RUNNING'):
            ops.backup(release['data'], release['data'].parent/'blocked.zip')


def test_rate_limit_has_retry_and_no_credential_echo(release):
    with TestClient(create_production_app(),base_url='https://learn.example.org') as client:
        for _ in range(10):
            assert client.post('/api/v1/auth/login',json={'site_id':'nonexistent','username':'nobody','password':'not-a-real-password'}).status_code == 401
        result=client.post('/api/v1/auth/login',json={})
        assert result.status_code == 429 and result.headers['retry-after']=='60'
        assert 'password' not in result.text


def test_backup_restore_includes_blobs_and_full_existing_db(release):
    data=release['data']; (data/'blobs').mkdir(); (data/'blobs'/'evidence').write_text('fictional artifact')
    conn=sqlite3.connect(data/'hub.sqlite3'); conn.execute("CREATE TABLE synthetic_evidence(id TEXT)"); conn.execute("INSERT INTO synthetic_evidence VALUES ('fictional')");conn.commit();conn.close()
    snapshot=data.parent/'snapshot.zip'; result=ops.backup(data,snapshot)
    assert result['files']==2 and snapshot.stat().st_mode & 0o777 == 0o600
    target=data.parent/'restored'; restored=ops.restore(snapshot,target)
    assert restored['schema_versions']==[v for v,_ in MIGRATIONS]
    assert (target/'blobs'/'evidence').read_text()=='fictional artifact'
    conn=sqlite3.connect(target/'hub.sqlite3'); assert conn.execute('SELECT id FROM synthetic_evidence').fetchone()[0]=='fictional';conn.close()
    with pytest.raises(ValueError,match='EMPTY_DIRECTORY'):ops.restore(snapshot,target)
    # Tamper detection occurs before any output directory or partial DB is created.
    bad=data.parent/'bad.zip'
    with zipfile.ZipFile(snapshot) as source, zipfile.ZipFile(bad,'w') as out:
        for name in source.namelist():out.writestr(name,b'tampered' if name=='blobs/evidence' else source.read(name))
    with pytest.raises(ValueError,match='HASH_MISMATCH'):ops.restore(bad,data.parent/'must-not-exist')
    assert not (data.parent/'must-not-exist').exists()


def test_migration_is_backup_bound_and_rehearsed(release):
    with pytest.raises(ValueError,match='REQUIRES_BACKUP'):ops.migration(release['data'],None)
    result=ops.migration(release['data'],release['data'].parent/'before-migration.zip')
    assert result['migrations_applied']==[] and result['rehearsal_verified'] is True
    fresh=release['data'].parent/'fresh';result=ops.migration(fresh,None)
    assert result['migrations_applied']==[v for v,_ in MIGRATIONS]


def test_config_production_cannot_inherit_development_seed_flag(release,monkeypatch):
    monkeypatch.setenv('WAIKE_ENV','development')
    monkeypatch.setenv('WAIKE_SEED_TEST_FIXTURES','true')
    app=create_app(config=HubConfig(environment='production'),db_path=release['data']/'config-prod.sqlite3')
    assert app.state.seeded_test_fixtures is False
    assert app.state.db.execute('SELECT count(*) FROM users').fetchone()[0]==0
    app.state.db.close()


def test_reserved_fixture_database_refused(release):
    conn=sqlite3.connect(release['data']/'hub.sqlite3')
    conn.execute("INSERT INTO sites VALUES ('site-alpha','Synthetic fixture','2000-01-01')");conn.commit();conn.close()
    with pytest.raises(ValueError,match='SYNTHETIC_FIXTURE_DATABASE_FORBIDDEN'):settings()


def test_shared_connection_requests_are_serialized():
    import asyncio
    import httpx
    active=0; maximum=0
    async def backend(scope,receive,send):
        nonlocal active,maximum
        active+=1;maximum=max(maximum,active)
        await asyncio.sleep(0.01)
        active-=1
        await send({'type':'http.response.start','status':200,'headers':[]})
        await send({'type':'http.response.body','body':b'ok'})
    async def run():
        transport=httpx.ASGITransport(app=ProductionBoundary(backend,origin='https://learn.example.org'))
        async with httpx.AsyncClient(transport=transport,base_url='https://learn.example.org') as client:
            replies=await asyncio.gather(*[client.post('/api/v1/probe',json={}) for _ in range(8)])
            assert all(r.status_code==200 for r in replies)
    asyncio.run(run())
    assert maximum==1


def test_tree_hash_preserves_internal_canonical_links_and_refuses_external(tmp_path):
    root=tmp_path/'source';root.mkdir();(root/'real').mkdir();(root/'real'/'lesson').write_text('canonical')
    before=tree_hash(root);(root/'alias').symlink_to('real',target_is_directory=True)
    assert tree_hash(root)!=before
    outside=tmp_path/'private';outside.write_text('outside source')
    (root/'forbidden').symlink_to(outside)
    with pytest.raises(ValueError,match='EXTERNAL_SYMLINK_FORBIDDEN'):tree_hash(root)
