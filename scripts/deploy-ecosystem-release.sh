#!/usr/bin/env bash
set -euo pipefail

# Feature freeze: legacy source-copy/Compose deployment is not approved.
# This entry point deliberately performs no external command or file mutation.
# Exact runtime reconciliation, isolated restore and rollback evidence must be
# reviewed before a separate immutable, single-service apply path is introduced.
printf '%s\n' 'BLOCKED: release HOLD — runtime provenance and verified rollback are required.' >&2
printf '%s\n' 'Use the read-only Hub release runbook; this script cannot deploy.' >&2
exit 78
