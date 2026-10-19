#!/usr/bin/env python3
"""Explicit owner OAuth consent. Never starts a workforce job or sends a message."""
import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

OWNER = 'vision79slu@gmail.com'
SCOPES = (
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events.owned',
)
TOKEN_URL = 'https://oauth2.googleapis.com/token'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def google_json(url, *, form=None, token=None):
    if url not in (TOKEN_URL, 'https://gmail.googleapis.com/gmail/v1/users/me/profile',
                   'https://www.googleapis.com/calendar/v3/calendars/primary'):
        raise ValueError('Endpoint not allowed')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = urlencode(form).encode() if form else None
    request = Request(url, data=data, headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            return json.load(response)
    except (HTTPError, URLError, ValueError):
        # OAuth responses can contain codes/tokens: never echo response or request details.
        raise RuntimeError('Google authorization request failed; verify APIs, consent and scopes') from None


def private_client(file):
    path = Path(file)
    if path.is_symlink():
        raise ValueError('Client file must not be a symlink')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'r') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('Client JSON must be owned by this user and chmod 600')
        client = json.load(handle).get('installed')
    if not isinstance(client, dict) or not all(isinstance(client.get(k), str) and client[k] for k in ('client_id', 'client_secret')):
        raise ValueError('A dedicated Google Desktop app OAuth client JSON is required')
    return {k: client[k] for k in ('client_id', 'client_secret')}


def consent_url(client_id, redirect_uri, state, verifier):
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': client_id, 'redirect_uri': redirect_uri, 'response_type': 'code',
        'scope': ' '.join(SCOPES), 'access_type': 'offline', 'prompt': 'consent',
        'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
        'login_hint': OWNER, 'include_granted_scopes': 'false',
    })


def callback_code(path, expected_state):
    parsed = urlsplit(path)
    if parsed.path != '/callback' or len(path) > 10000:
        raise ValueError('Invalid callback path')
    values = parse_qs(parsed.query, keep_blank_values=True)
    if len(values.get('state', [])) != 1 or not hmac.compare_digest(values['state'][0], expected_state):
        raise ValueError('OAuth state mismatch')
    if 'error' in values or len(values.get('code', [])) != 1 or not values['code'][0]:
        raise ValueError('Consent denied or code missing')
    return values['code'][0]


def verified_credentials(client, tokens, request=google_json):
    if not isinstance(tokens.get('access_token'), str) or not isinstance(tokens.get('refresh_token'), str) or not tokens['refresh_token']:
        raise ValueError('Offline grant missing; no credentials saved')
    granted = set(str(tokens.get('scope', '')).split())
    if granted != set(SCOPES):
        raise ValueError('Exact requested scopes were not granted; no credentials saved')
    token = tokens['access_token']
    profile = request('https://gmail.googleapis.com/gmail/v1/users/me/profile', token=token)
    calendar = request('https://www.googleapis.com/calendar/v3/calendars/primary', token=token)
    if str(profile.get('emailAddress', '')).lower() != OWNER or str(calendar.get('id', '')).lower() != OWNER:
        raise ValueError('Wrong Google account; no credentials saved')
    # Do not persist the short-lived access token; the host broker obtains it when needed.
    return {'schema': 1, 'owner': OWNER, **client, 'refresh_token': tokens['refresh_token'],
            'scopes': sorted(granted), 'authorized_at': int(time.time())}


def save_credentials(directory, credentials):
    directory = Path(directory).absolute()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError('Credential directory must be owned by this user and chmod 700')
    target = directory / 'credentials.json'
    # Deliberately no replacement: prevent accidental destruction of a working grant.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as handle:
            json.dump(credentials, handle)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        parent_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, help='chmod 600 Desktop OAuth client JSON')
    parser.add_argument('--directory', default=str(Path.home() / '.config/v79-workforce/google'))
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError('Choose a non-privileged local port')
    client = private_client(args.client)
    if (Path(args.directory) / 'credentials.json').exists():
        raise ValueError('Credentials already exist; no replacement performed')
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Request URLs contain the OAuth code.

        def do_GET(self):
            try:
                code = callback_code(self.path, state)
            except ValueError:
                self.send_response(400)
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(b'Authorization callback rejected. Return to the terminal.')
                return
            received['code'] = code
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(b'Consent received. Check the terminal for account verification. You may close this tab.')

    redirect_uri = f'http://127.0.0.1:{args.port}/callback'
    with HTTPServer(('127.0.0.1', args.port), Callback) as server:
        server.timeout = 1
        print('MODE=EXPLICIT_GOOGLE_CONSENT_ONLY', flush=True)
        print('Open this URL in your own browser. Use the SSH loopback tunnel when running on v79sl.', flush=True)
        print(consent_url(client['client_id'], redirect_uri, state, verifier), flush=True)
        deadline = time.monotonic() + 600
        while 'code' not in received and time.monotonic() < deadline:
            server.handle_request()
    if 'code' not in received:
        raise ValueError('Authorization timed out; no credentials saved')
    tokens = google_json(TOKEN_URL, form={**client, 'code': received['code'], 'code_verifier': verifier,
                        'redirect_uri': redirect_uri, 'grant_type': 'authorization_code'})
    credentials = verified_credentials(client, tokens)
    target = save_credentials(args.directory, credentials)
    print('GOOGLE_ACCOUNT=VERIFIED_OWNER')
    print('OFFLINE_CREDENTIALS=SAVED_PRIVATE')
    print('CREDENTIAL_FILE=' + str(target))
    print('WORKFORCE_ENABLED=NO')
    print('EMAILS_OR_APPOINTMENTS_CHANGED=NO')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        # Only locally generated messages; no upstream HTTP bodies or token values.
        if isinstance(error, (ValueError, RuntimeError)) and not isinstance(error, json.JSONDecodeError):
            print('STOP=' + str(error), file=sys.stderr)
        else:
            print('STOP=Local file, port or credential storage unavailable', file=sys.stderr)
        sys.exit(1)
