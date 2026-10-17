# Owner-authorized Hub/Tiquet rollout — 17 October 2026

The founder authorized portfolio merges/deployment on 17 October and subsequently
approved preparing this helper. This is an explicit alternative to the generic
Hub deployment script, which correctly refuses the pinned live WiPay stack.
It does not remove that guard or weaken runtime authentication or tenant controls.

## Options reviewed

1. Generic source sync + base Compose: rejects the live pinned overlays and risks
   dropping effective settings; unsuitable.
2. Recreate the whole Compose project: risks databases, tokens and the separate
   business-agent release; unsuitable.
3. **Chosen:** freeze the exact current effective Compose models, change only the
   selected app images, recreate only the two app services with no dependencies.

## Execution and evidence

Run `scripts/portfolio-pinned-rollout.py` on non-root Acer, after verifying its Git
blob from a pinned commit. It uses the established `firelion@v79sl` SSH identity
with strict host checking. Source candidates are Hub `c2681be42ad0dd68dbabebabb206273a9ea6c817`
and Tiquet `7da53ebb71530366168bd72a7efd52b57d34a23c`.

The helper requires the exact inventoried original images, ordered 13 Hub layers
and one Tiquet effective file, matching file hashes, healthy apps, unchanged
rendered environment, MFA, entitlement recheck and shared launch secret. It
rejects ambient Compose/Docker/Git environment overrides and published app ports.
Literal dollar signs in inspected environment/command values are escaped for
Compose reload, and rendered environment is compared again before shutdown. An
actual Compose serialization test runs in GitHub CI without starting containers.
Docker Compose 5.5.0 config serialization explicitly doubles dollars:
https://github.com/docker/compose/blob/v5.5.0/cmd/compose/config.go

It records the actual candidate image IDs after sequential builds from exact Git
commits, with revision labels. It never retags or deletes original images.

Both builds and encryption of the old app images complete while apps still run.
Before shutdown, active V79 workforce/release/task user timers are paused, and
associated services must be idle; only timers originally active are resumed on
success or failure. Then both apps stop briefly; databases, agent, proxy and other apps remain running.
Each database gets a custom-format pg_dump. Every mounted app destination is
archived from its stopped container, including private files. Streams are encrypted
directly to the existing R1 public key fingerprint
`484CF39CE37A02884497AD9C41A17102D2842ECE`, with no plaintext checkpoint stream on disk.
The remote host receives only the public key. Private frozen Compose/runtime
metadata remain in the mode-0700 remote run directory and are never printed.

Only selected image IDs differ between the frozen original and candidate models.
Every original file remains unchanged. `up -d --no-deps --no-build --pull never`
targets a single service at a time. Docker health checks must pass. The post-switch
runtime comparison includes complete environment, command, entrypoint, user,
working directory, exposed ports, healthcheck, host configuration, mounts and
network membership; dynamic container IDs/IPs and Compose/image labels are excluded.
Other pre-existing containers must retain their IDs/images/status.

On failure after shutdown, restart untouched apps or recreate attempted apps with
their original images, in reverse order. Report rollback failure explicitly. This
is **image rollback**, not automatic database or application-state rollback:
startup can apply schema/state changes. Never overwrite live data automatically.
The encrypted checkpoint is retained for separately reviewed restoration if needed.

The remote worker is detached, with a single-host rollout lock, so disconnecting
the Acer does not kill recovery. The Acer prints its run directory immediately.
Reconnect using the same pinned helper:

```sh
python3 /path/to/verified-helper.py --resume /home/firelion/v79-portfolio-rollout.XXXXXXXX
```

Resume only monitors/copies; it cannot launch a second deployment. A three-hour
monitor timeout does not terminate the server worker. Do not run another deployment
while that worker is active. SIGTERM during the guarded mutation scope triggers
rollback; power loss/SIGKILL cannot be trapped and require manual reconciliation.

At completion, encrypted artifacts and manifest are copied to a new private Acer
checkpoint directory. Every ciphertext hash and full GPG decryption stream is
checked without writing plaintext to disk. Capture/decryption is not a restore
rehearsal. Neither the original R1 recovery directory nor production volumes are
deleted, replaced, imported or restored by this helper.

## Acceptance limits

Source-only synthetic tests cover lifecycle failures and runtime guard behavior;
they do not constitute a server deployment. Server execution must report genuine
results before marking either release deployed. New features remain governed by
the unchanged live feature flags. The business-agent image is deliberately not
updated by this Hub/Tiquet app release. Historical scanner findings remain separate
unresolved review items; this change does not claim scanner clearance.

This checkpoint covers Hub/Tiquet, not the complete portfolio. Full encrypted
portfolio backup, isolated new-release restoration, authenticated MFA/SSO,
revocation, two-tenant security tests and real Sentinel monitoring are outstanding.
`CUSTOMER_RELEASE=NO_GO` remains unconditional.
