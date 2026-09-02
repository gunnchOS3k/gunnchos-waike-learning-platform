# Compatibility contract

Packages carry a `compatibility` object validated against `contracts/schemas/compatibility_manifest.v1.json`.

## Rules

1. Unknown or mismatched **major** schema versions → `INCOMPATIBLE_SCHEMA_MAJOR`.
2. Platform version below `platform_min` → `PLATFORM_TOO_OLD`.
3. Platform version at/above `platform_max_exclusive` → `PLATFORM_TOO_NEW`.
4. Content version below an already-installed protected version → `SCHEMA_DOWNGRADE` / downgrade rejection unless an explicit development override is supplied.
5. Bad signature / tampered hashes → `BAD_SIGNATURE` / `TAMPERED_CONTENT`.
6. Wrong pack role for the install path → `WRONG_ROLE`.
7. Unknown track/module ID → `UNKNOWN_MODULE`.

All rejections use typed `RejectionReason` values suitable for UI display without leaking secrets.
