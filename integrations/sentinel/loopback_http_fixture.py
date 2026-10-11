"""EXCLUSIVELY a disposable loopback HTTP fixture for G2 staging tests.

Not the Acer Sentinel NOC. NEVER import or mount this file in production.
- Binds 127.0.0.1 on OS-selected ephemeral port (never public interfaces).
- Receives ephemeral TEST keys + synthetic observation on stdin.
- Emits only a port number on stdout, never keys/data.
- Runs until the test parent terminates it; uses ONLY a disposable\n  private temporary SQLite nonce ledger (no real NOC or account writes).
- Rejects cookies, Authorization, mutation routes and any body.
The actual NOC integration needs a separate independent security review.
"""
from __future__ import annotations

import base64
import json
import sys
import signal
import tempfile
import threading
from pathlib import Path
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography.hazmat.primitives import serialization

from read_only_dispatcher import (
    IsolatedReadOnlySentinelDispatcher, TrustedReadCaller,
)
from source_signer import TrustedSourceSigner
from sqlite_replay_guard import SqliteNonceReplayGuard

HEADER_NAMES = (
    "X-V79-Read-Organization",
    "X-V79-Read-Key-Id",
    "X-V79-Read-Request-Id",
    "X-V79-Read-Issued-At",
    "X-V79-Read-Signature",
)
MAX_INPUT = 60_000


def main() -> None:
    line = sys.stdin.buffer.readline(MAX_INPUT + 1)
    if len(line) > MAX_INPUT or not line.endswith(b"\n"):
        raise ValueError("Invalid bounded synthetic fixture")
    fixture = json.loads(line)
    private_key = serialization.load_pem_private_key(
        fixture["privateKeyPem"].encode("ascii"), password=None
    )
    hmac_key = base64.urlsafe_b64decode(fixture["readHmacKey"] + "=")
    now = datetime.fromisoformat(fixture["now"].replace("Z", "+00:00"))
    replay_directory = tempfile.TemporaryDirectory(prefix="v79-g2-test-nonces-")
    signed = IsolatedReadOnlySentinelDispatcher(
        TrustedReadCaller("v79founder", "sentinel-g2-test", hmac_key),
        TrustedSourceSigner("sentinel-g2-test", "v79founder", private_key),
        lambda: fixture["missionSnapshot"],
        clock=lambda: now,
        replay_guard=SqliteNonceReplayGuard(Path(replay_directory.name) / "used.sqlite3"),
    )

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"
        server_version = "G2-TEST-ONLY"
        sys_version = ""

        def log_message(self, *args):
            pass  # avoid recording incoming HMAC headers and private data

        def _respond(self, code, data):
            message = json.dumps(data, separators=(",", ":")).encode("utf8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

        def _handle(self):
            # Only safe loopback test requests with one copy of each protocol
            # header. Never pass HTTP protocol/library headers to the signer.
            if (self.headers.get("Cookie") is not None
                or self.headers.get("Authorization") is not None
                or self.headers.get("Transfer-Encoding") is not None
                or self.headers.get("Content-Length") not in (None, "0")
                or any(len(self.headers.get_all(name) or []) != 1 for name in HEADER_NAMES)):
                return self._respond(401, {"error": "Unauthorized"})
            exact = {name: self.headers.get(name) for name in HEADER_NAMES}
            status, result = signed.get(self.command, self.path, exact)
            return self._respond(status, result)

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_DELETE = _handle
        do_PATCH = _handle
        do_OPTIONS = _handle

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    def _shutdown(_signal, _frame):
        # SIGTERM from the parent test must clean disposable SQLite state.
        # shutdown() cannot run in the same thread as serve_forever().
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, _shutdown)
    try:
        print(server.server_address[1], flush=True)  # Port only; no credentials
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        replay_directory.cleanup()


if __name__ == "__main__":
    main()
