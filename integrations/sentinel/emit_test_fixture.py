"""Synthetic only: stdin-to-stdout fixture for Python -> Node Ed25519 tests.

No HTTP listener. No file writes. Test private key comes from an ephemeral
Node-generated key pair and is never returned or stored. DO NOT DEPLOY.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime
from cryptography.hazmat.primitives import serialization

from source_signer import (
    TrustedSourceSigner, aggregate_mission_snapshot, sign_aggregate_for_challenge
)


def main() -> None:
    raw = sys.stdin.buffer.read(32_001)
    if len(raw) > 32_000:
        raise ValueError("Fixture too large")
    inp = json.loads(raw)
    key = serialization.load_pem_private_key(inp["privateKeyPem"].encode("ascii"), password=None)
    signer = TrustedSourceSigner(
        key_id="sentinel-g2-test",
        organization_id="v79founder",
        private_key=key,
    )
    now = datetime.fromisoformat(inp["now"].replace("Z", "+00:00"))
    agg = aggregate_mission_snapshot(inp["missionSnapshot"], now=now)
    envelope = sign_aggregate_for_challenge(agg, inp["challenge"], signer, now=now)
    sys.stdout.write(json.dumps(envelope, separators=(",", ":")))


if __name__ == "__main__":
    main()
