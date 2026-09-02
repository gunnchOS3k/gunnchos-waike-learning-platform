# Instructor package cryptography (PR1)

## Separation

Learner packages are signed (Ed25519) and contain only learner-authorized material.

Instructor packages are a **separate** AES-256-GCM encrypted artifact. Hidden UI is not a security boundary.

## AES-256-GCM nonce policy

Every encryption under a given key MUST use a **unique cryptographically secure random nonce** (`os.urandom(12)`).

Forbidden nonce sources:

- `SOURCE_DATE_EPOCH`
- static labels / pack IDs alone
- file paths
- deterministic package metadata hashes used as the sole nonce input

Reusing a nonce under the same AES-GCM key is a critical cryptographic failure mode.

## Reproducibility contract

| Artifact | Reproducible under `SOURCE_DATE_EPOCH` + test keys? |
|----------|-----------------------------------------------------|
| Learner pack zip / signed manifest | **Yes** — byte-identical expected |
| Instructor canonical plaintext (pre-encryption zip/payload) | **Yes** — hash compared |
| Instructor AES-GCM ciphertext / nonce | **No** — must differ across encrypts |

Tests prove:

1. learner hashes match across two compiles;
2. instructor plaintext hashes match across two compiles;
3. nonces/ciphertexts differ across two encrypts;
4. both ciphertexts decrypt to the same plaintext;
5. wrong key / tampered ciphertext fail closed.

## Keys

Automated tests use explicitly labeled `TEST_ONLY_*` fixture keys.

Release mode must fail closed if only `TEST_ONLY` signing material is configured.

Production key ceremony is an external/human gate — not part of PR1.
