# Interrupted current P1 capture: evidence and next boundary

The owner-approved capture t3TEQV5N produced all twelve expected encrypted files. The first Tiquet resume failed (Docker exit 128, not OOM); its cause remains unknown. Emergency recovery verified both original container IDs healthy and resumed originally active timers. Do not classify this as a successful unattended capture.

The owner copied all twelve ciphertext files to Acer `~/V79-Portfolio-Checkpoints/p1-interrupted-t3TEQV5N.qmLDzVUD`. Server-generated SHA256SUMS matched 12/12; full GPG stream decryption to /dev/null passed 12/12. No final capture manifest exists. Preserve this set, the server run and earlier immutable backups.

Three approaches: recapture with another production pause; adapt the old restore runner immediately; audit and reuse existing ciphertext before building a format-specific restore adapter. Choose the third to avoid another pause and avoid treating old compressed-mount/filename assumptions as acceptance of this format.

The new audit runs only on Acer with no active swap. It rechecks the fixed backup's ciphertext hashes, parses runtime/config metadata in bounded memory, maps eight archives by captured Mounts order, rejects unsafe TAR entries, verifies two custom PostgreSQL dump magic headers, and checks four Docker manifest config SHA256 identities against captured runtime plus all declared layer references. It extracts nothing, imports nothing and starts no containers. Secret-bearing metadata and file paths are never printed. GPG stdout is consumed through EOF to verify authenticated decryption status.

Limits: config identity is internal consistency, not an independent release receipt attestation; no OCI graph or uncompressed layer diff-ID attestation is claimed. A PGDMP header is not a pg_restore test. Archive structure is not full current-set recovery or MFA acceptance. The next adapter must use this exact format, validate full image provenance before any permitted import, keep original token mounts excluded, use synthetic credentials and disconnected RAM-only containers, prove cleanup and swap restoration, and retain NO_GO.

Red team: do not recreate production containers, weaken start identity checks, treat absent logs as a transient-error diagnosis, or retry Docker starts indefinitely. The current helper masks a primary capture exception if finally-resume also fails; separate failure evidence must be added before any future approved recapture. Do not issue a new production pause merely to produce a missing manifest.
