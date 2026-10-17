"""Offline authenticated request/response fixture for G2 cross-language tests.

Never start a server, save keys, connect to NOC, or use production credentials.
All keys and observations are synthetic in-memory test inputs only.
"""
from __future__ import annotations
import base64
import json
import sys
from datetime import datetime

from cryptography.hazmat.primitives import serialization

from read_only_dispatcher import IsolatedReadOnlySentinelDispatcher, TrustedReadCaller
from source_signer import TrustedSourceSigner


def main() -> None:
    raw = sys.stdin.buffer.read(60_001)
    if len(raw) > 60_000:
        raise ValueError("Fixture input too large")
    inp = json.loads(raw)
    private_key = serialization.load_pem_private_key(
        inp["privateKeyPem"].encode("ascii"), password=None
    )
    shared = base64.urlsafe_b64decode(inp["readHmacKey"] + "=")
    now = datetime.fromisoformat(inp["now"].replace("Z", "+00:00"))
    gate = IsolatedReadOnlySentinelDispatcher(
        TrustedReadCaller("v79founder", "sentinel-g2-test", shared),
        TrustedSourceSigner("sentinel-g2-test", "v79founder", private_key),
        lambda: inp["missionSnapshot"],
        clock=lambda: now, allow_in_memory_for_tests=True,
    )
    request = inp["readRequest"]
    status, response = gate.get(request["method"], request["path"], request["headers"])
    sys.stdout.write(json.dumps({"status": status, "body": response}, separators=(",", ":")))


if __name__ == "__main__":
    main()
