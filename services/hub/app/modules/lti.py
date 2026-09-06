"""LTI 1.3 launch foundation — registration, OIDC state/nonce, JWT/JWK validation.

Digital foundation only. Does NOT claim external LMS certification.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import sqlite3
import time
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
from jwt.exceptions import InvalidTokenError as JWTError

from app.auth import Actor, Role
from app.modules.assessment_lifecycle import ServiceError, _id, _now, _row

# Role mapping: never auto-create site_admin from arbitrary LTI roles.
LTI_ROLE_MAP = {
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner": Role.LEARNER,
    "Learner": Role.LEARNER,
    "Student": Role.LEARNER,
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor": Role.INSTRUCTOR,
    "Instructor": Role.INSTRUCTOR,
    "Faculty": Role.INSTRUCTOR,
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Mentor": Role.GRADER,
    "TeachingAssistant": Role.GRADER,
    "Administrator": Role.INSTRUCTOR,  # capped — no site_admin escalation
}

ALLOWED_JWT_ALGS = ("RS256",)
STATE_TTL_SECONDS = 600  # 10 minutes
JWKS_FETCH_TIMEOUT = 10


def generate_test_rsa_keypair() -> tuple[str, str, dict[str, Any]]:
    """CI/test keys only — never commit production private keys."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    numbers = key.public_key().public_numbers()

    def b64url_uint(val: int) -> str:
        length = (val.bit_length() + 7) // 8
        return (
            __import__("base64")
            .urlsafe_b64encode(val.to_bytes(length, "big"))
            .rstrip(b"=")
            .decode("ascii")
        )

    jwk = {
        "kty": "RSA",
        "kid": "gate-c-test-key",
        "use": "sig",
        "alg": "RS256",
        "n": b64url_uint(numbers.n),
        "e": b64url_uint(numbers.e),
    }
    return private_pem, public_pem, jwk


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_safe_jwks_url(url: str, *, resolve_dns: bool = False) -> str:
    """SSRF controls: HTTPS only; block private/link-local/metadata/localhost/file."""
    if not url or not isinstance(url, str):
        raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    parsed = urlsplit(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme == "file":
        raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    if scheme != "https":
        raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".localhost"):
        raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    if host.startswith("169.254.") or host == "metadata":
        raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    try:
        literal = ipaddress.ip_address(host)
        if _is_blocked_ip(literal):
            raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    except ValueError:
        pass
    if resolve_dns:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise ServiceError("LTI_JWKS_URL_BLOCKED", 400) from e
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if _is_blocked_ip(ip):
                raise ServiceError("LTI_JWKS_URL_BLOCKED", 400)
    return url


def default_fetch_jwks(url: str) -> dict[str, Any]:
    """Production JWKS fetch over HTTPS with SSRF gate."""
    safe = assert_safe_jwks_url(url, resolve_dns=True)
    req = urllib.request.Request(safe, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=JWKS_FETCH_TIMEOUT) as resp:  # noqa: S310
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ServiceError("LTI_JWKS_FETCH_FAILED", 400) from e
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ServiceError("LTI_JWKS_FETCH_FAILED", 400) from e
    if not isinstance(data, dict) or "keys" not in data:
        raise ServiceError("LTI_JWKS_FETCH_FAILED", 400)
    return data

def _normalize_uri(uri: str) -> tuple[str, str, str]:
    p = urlsplit(uri)
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return (p.scheme.lower(), (p.netloc or "").lower(), path)


def uris_exact_match(a: str, b: str) -> bool:
    """Exact origin + path match (query/fragment ignored)."""
    return _normalize_uri(a) == _normalize_uri(b)


def _parse_iso(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class LtiService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        fetch_jwks: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.conn = conn
        self._test_private: str | None = None
        self._test_jwk: dict[str, Any] | None = None
        # Injectable for tests; production default never falls back to test keys.
        self.fetch_jwks: Callable[[str], dict[str, Any]] = fetch_jwks or default_fetch_jwks

    def support_matrix(self) -> dict[str, Any]:
        return {
            "standard": "LTI 1.3 foundation",
            "claim": "NOT_LTI_CERTIFIED",
            "supported": [
                "tool/platform registration",
                "issuer/client/deployment",
                "OIDC login initiation",
                "state/nonce",
                "JWT validation (iss/aud/exp/nonce/deployment)",
                "JWKS/JWK",
                "role mapping (capped)",
                "target-link URI validation",
            ],
            "unsupported": [
                "Deep Linking 2.0 full",
                "Assignment and Grade Services full",
                "Names and Role Provisioning full",
                "external LMS certification",
            ],
        }

    def ensure_test_keys(self) -> dict[str, Any]:
        """Test helper for minting tokens — NEVER used by production validate path."""
        if self._test_private is None:
            priv, _pub, jwk = generate_test_rsa_keypair()
            self._test_private = priv
            self._test_jwk = jwk
        return {"jwk": self._test_jwk, "kid": "gate-c-test-key"}

    def register(
        self,
        actor: Actor,
        *,
        issuer: str,
        client_id: str,
        deployment_id: str,
        auth_login_url: str,
        auth_token_url: str,
        jwks_url: str,
        target_link_uri: str,
    ) -> dict[str, Any]:
        if not actor.is_site_admin:
            raise ServiceError("LTI_FORBIDDEN", 403)
        assert_safe_jwks_url(jwks_url)
        rid = _id("ltireg")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO lti_registrations(
              registration_id, site_id, issuer, client_id, deployment_id,
              auth_login_url, auth_token_url, jwks_url, target_link_uri, active, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,1,?)
            """,
            (
                rid,
                actor.site_id,
                issuer,
                client_id,
                deployment_id,
                auth_login_url,
                auth_token_url,
                jwks_url,
                target_link_uri,
                now,
            ),
        )
        self.conn.commit()
        return {"registration_id": rid, "issuer": issuer, "client_id": client_id}

    def oidc_login_init(self, registration_id: str, login_hint: str = "") -> dict[str, Any]:
        reg = _row(
            self.conn,
            "SELECT * FROM lti_registrations WHERE registration_id=? AND active=1",
            (registration_id,),
        )
        if reg is None:
            raise ServiceError("LTI_UNKNOWN_REGISTRATION", 404)
        state = uuid.uuid4().hex
        nonce = uuid.uuid4().hex
        now = _now()
        self.conn.execute(
            "INSERT INTO lti_states(state, registration_id, nonce, created_at) VALUES (?,?,?,?)",
            (state, registration_id, nonce, now),
        )
        self.conn.commit()
        return {
            "authorization_redirect": {
                "url": reg["auth_login_url"],
                "client_id": reg["client_id"],
                "redirect_uri": reg["target_link_uri"],
                "login_hint": login_hint,
                "state": state,
                "nonce": nonce,
                "scope": "openid",
                "response_type": "id_token",
                "response_mode": "form_post",
            }
        }

    def map_roles(self, role_claims: list[str]) -> Role:
        mapped: list[Role] = []
        for claim in role_claims:
            role = LTI_ROLE_MAP.get(claim)
            if role is None:
                for k, v in LTI_ROLE_MAP.items():
                    if claim.endswith(k) or k.endswith(claim):
                        role = v
                        break
            if role is not None:
                mapped.append(role)
        if not mapped:
            raise ServiceError("LTI_UNSUPPORTED_ROLE", 400)
        if Role.SITE_ADMIN in mapped:
            mapped = [r for r in mapped if r != Role.SITE_ADMIN] or [Role.INSTRUCTOR]
        for pref in (Role.INSTRUCTOR, Role.GRADER, Role.LEARNER):
            if pref in mapped:
                return pref
        return mapped[0]

    def _consume_state_atomic(self, *, state: str, registration_id: str) -> sqlite3.Row:
        cutoff_dt = datetime.now(tz=timezone.utc) - timedelta(seconds=STATE_TTL_SECONDS)
        cutoff = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        now = _now()
        cur = self.conn.execute(
            """
            UPDATE lti_states
               SET consumed_at=?
             WHERE state=? AND registration_id=?
               AND consumed_at IS NULL
               AND created_at > ?
            """,
            (now, state, registration_id, cutoff),
        )
        if cur.rowcount != 1:
            st = _row(
                self.conn,
                "SELECT * FROM lti_states WHERE state=? AND registration_id=?",
                (state, registration_id),
            )
            if st is None:
                raise ServiceError("LTI_STATE_MISMATCH", 400)
            if st["consumed_at"]:
                raise ServiceError("LTI_STATE_MISMATCH", 400)
            try:
                created = _parse_iso(st["created_at"])
            except ValueError as e:
                raise ServiceError("LTI_STATE_MISMATCH", 400) from e
            if created <= cutoff_dt:
                raise ServiceError("LTI_STATE_EXPIRED", 400)
            raise ServiceError("LTI_STATE_MISMATCH", 400)
        st = _row(
            self.conn,
            "SELECT * FROM lti_states WHERE state=? AND registration_id=?",
            (state, registration_id),
        )
        assert st is not None
        return st

    def _resolve_jwks(
        self,
        reg: sqlite3.Row,
        jwks: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Resolve JWKS for validation. Never falls back to ensure_test_keys()."""
        if jwks is not None:
            return jwks
        return self.fetch_jwks(reg["jwks_url"])

    def _map_or_reuse_identity(
        self,
        *,
        registration_id: str,
        site_id: str,
        subject: str,
        display_name: str,
        mapped_role: Role,
        now: str,
    ) -> str:
        existing = _row(
            self.conn,
            """
            SELECT user_id FROM lti_external_identities
             WHERE registration_id=? AND subject=?
            """,
            (registration_id, subject),
        )
        if existing is not None:
            return str(existing["user_id"])

        mapped_user = _id("ltiu")
        self.conn.execute(
            """
            INSERT INTO users(user_id, site_id, username, display_name, password_hash, disabled, created_at)
            VALUES (?,?,?,?,?,0,?)
            """,
            (
                mapped_user,
                site_id,
                f"lti:{subject}"[:80],
                display_name[:120],
                "!",
                now,
            ),
        )
        self.conn.execute(
            """
            INSERT INTO role_assignments(assignment_id, user_id, site_id, role, active, created_at)
            VALUES (?,?,?,?,1,?)
            """,
            (_id("ra"), mapped_user, site_id, mapped_role.value, now),
        )
        self.conn.execute(
            """
            INSERT INTO lti_external_identities(
              identity_id, registration_id, site_id, subject, user_id, created_at
            ) VALUES (?,?,?,?,?,?)
            """,
            (_id("ltiid"), registration_id, site_id, subject, mapped_user, now),
        )
        return mapped_user

    def validate_launch(
        self,
        *,
        registration_id: str,
        id_token: str,
        state: str,
        jwks: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        reg = _row(
            self.conn,
            "SELECT * FROM lti_registrations WHERE registration_id=? AND active=1",
            (registration_id,),
        )
        if reg is None:
            raise ServiceError("LTI_UNKNOWN_REGISTRATION", 404)

        # Atomic consume with TTL before crypto work to prevent reuse races.
        st = self._consume_state_atomic(state=state, registration_id=registration_id)

        keys = self._resolve_jwks(reg, jwks)
        try:
            header = jwt.get_unverified_header(id_token)
            alg = header.get("alg")
            if alg not in ALLOWED_JWT_ALGS:
                raise ServiceError("LTI_INVALID_SIGNATURE", 400)
            kid = header.get("kid")
            if not kid:
                raise ServiceError("LTI_MISSING_KID", 400)
            jwk = None
            for k in keys.get("keys", []):
                if k.get("kid") == kid:
                    jwk = k
                    break
            if jwk is None:
                raise ServiceError("LTI_INVALID_SIGNATURE", 400)
            pub = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
            claims = jwt.decode(
                id_token,
                key=pub,
                algorithms=list(ALLOWED_JWT_ALGS),
                audience=reg["client_id"],
                issuer=reg["issuer"],
            )
        except ServiceError:
            raise
        except JWTError as e:
            msg = str(e).lower()
            if "expire" in msg:
                raise ServiceError("LTI_EXPIRED", 400) from e
            if "audience" in msg:
                raise ServiceError("LTI_WRONG_AUDIENCE", 400) from e
            if "issuer" in msg:
                raise ServiceError("LTI_WRONG_ISSUER", 400) from e
            if "signature" in msg:
                raise ServiceError("LTI_INVALID_SIGNATURE", 400) from e
            raise ServiceError("LTI_INVALID_SIGNATURE", 400) from e

        nonce = claims.get("nonce")
        if nonce != st["nonce"]:
            raise ServiceError("LTI_STATE_MISMATCH", 400)
        if _row(self.conn, "SELECT nonce FROM lti_nonces WHERE nonce=?", (nonce,)):
            raise ServiceError("LTI_REUSED_NONCE", 400)

        deployment = claims.get(
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
        ) or claims.get("deployment_id")
        if deployment != reg["deployment_id"]:
            raise ServiceError("LTI_WRONG_DEPLOYMENT", 400)

        target = claims.get(
            "https://purl.imsglobal.org/spec/lti/claim/target_link_uri"
        ) or claims.get("target_link_uri")
        if target is None:
            target = reg["target_link_uri"]
        if not uris_exact_match(str(target), str(reg["target_link_uri"])):
            raise ServiceError("LTI_CROSS_SITE_TARGET", 400)

        roles_claim = claims.get(
            "https://purl.imsglobal.org/spec/lti/claim/roles", []
        )
        if isinstance(roles_claim, str):
            roles_claim = [roles_claim]
        mapped_role = self.map_roles(list(roles_claim))
        sub = claims.get("sub") or ""
        if not sub:
            raise ServiceError("LTI_INVALID_SIGNATURE", 400)

        now = _now()
        self.conn.execute(
            "INSERT INTO lti_nonces(nonce, registration_id, used_at) VALUES (?,?,?)",
            (nonce, registration_id, now),
        )
        launch_id = _id("ltilaunch")
        mapped_user = self._map_or_reuse_identity(
            registration_id=registration_id,
            site_id=reg["site_id"],
            subject=sub,
            display_name=claims.get("name") or f"LTI {sub}",
            mapped_role=mapped_role,
            now=now,
        )
        self.conn.execute(
            """
            INSERT INTO lti_launches(
              launch_id, registration_id, site_id, mapped_user_id, mapped_role,
              subject, target_link_uri, detail_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                launch_id,
                registration_id,
                reg["site_id"],
                mapped_user,
                mapped_role.value,
                sub,
                target,
                json.dumps({"iss": claims.get("iss"), "aud": claims.get("aud")}),
                now,
            ),
        )
        self.conn.commit()
        return {
            "launch_id": launch_id,
            "mapped_user_id": mapped_user,
            "mapped_role": mapped_role.value,
            "subject": sub,
            "target_link_uri": target,
            "certification_claim": False,
        }

    def mint_test_id_token(
        self,
        *,
        registration_id: str,
        nonce: str,
        roles: list[str],
        sub: str = "lti-subject-1",
        exp_delta: int = 300,
        issuer: str | None = None,
        audience: str | None = None,
        deployment_id: str | None = None,
        target_link_uri: str | None = None,
        mutate: dict[str, Any] | None = None,
        kid: str | None = "gate-c-test-key",
        algorithm: str = "RS256",
    ) -> str:
        self.ensure_test_keys()
        reg = _row(self.conn, "SELECT * FROM lti_registrations WHERE registration_id=?", (registration_id,))
        assert reg is not None
        claims = {
            "iss": issuer or reg["issuer"],
            "aud": audience or reg["client_id"],
            "sub": sub,
            "exp": int(time.time()) + exp_delta,
            "iat": int(time.time()),
            "nonce": nonce,
            "https://purl.imsglobal.org/spec/lti/claim/deployment_id": deployment_id
            or reg["deployment_id"],
            "https://purl.imsglobal.org/spec/lti/claim/roles": roles,
            "https://purl.imsglobal.org/spec/lti/claim/target_link_uri": target_link_uri
            or reg["target_link_uri"],
            "https://purl.imsglobal.org/spec/lti/claim/message_type": "LtiResourceLinkRequest",
            "https://purl.imsglobal.org/spec/lti/claim/version": "1.3.0",
            "name": "LTI Test User",
        }
        if mutate:
            claims.update(mutate)
        headers: dict[str, Any] = {}
        if kid is not None:
            headers["kid"] = kid
        return jwt.encode(
            claims,
            self._test_private,
            algorithm=algorithm,
            headers=headers or None,
        )
