import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

spec = importlib.util.spec_from_file_location('authorize', Path(__file__).parents[1] / 'scripts/workforce-google-authorize.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AuthorizationTests(unittest.TestCase):
    def test_pkce_state_and_fixed_scopes(self):
        url = module.consent_url('client', 'http://127.0.0.1:8765/callback', 'state', 'v' * 64)
        parsed = urlsplit(url)
        self.assertEqual(parsed.netloc, 'accounts.google.com')
        query = parse_qs(parsed.query)
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['state'], ['state'])
        self.assertEqual(set(query['scope'][0].split()), set(module.SCOPES))
        self.assertEqual(query['access_type'], ['offline'])

    def test_callback_cannot_accept_wrong_or_duplicate_state(self):
        self.assertEqual(module.callback_code('/callback?state=ok&code=synthetic', 'ok'), 'synthetic')
        for value in ['/callback?state=bad&code=x', '/callback?state=ok&state=ok&code=x', '/callback?state=ok&error=denied', '/different?state=ok&code=x']:
            with self.assertRaises(ValueError):
                module.callback_code(value, 'ok')

    def test_wrong_identity_or_missing_offline_grant_never_saved(self):
        tokens = {'access_token': 'access', 'refresh_token': 'refresh', 'scope': ' '.join(module.SCOPES)}
        def request(url, **kwargs):
            return {'emailAddress': 'other@example.com', 'id': module.OWNER}
        with self.assertRaises(ValueError):
            module.verified_credentials({}, tokens, request)
        with self.assertRaises(ValueError):
            module.verified_credentials({}, {**tokens, 'refresh_token': ''}, request)

    def test_private_storage_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            target = module.save_credentials(directory, {'refresh_token': 'synthetic'})
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                module.save_credentials(directory, {'refresh_token': 'replacement'})
            self.assertEqual(json.loads(target.read_text())['refresh_token'], 'synthetic')
            target.unlink()
            os.chmod(directory, 0o755)
            with self.assertRaises(ValueError):
                module.save_credentials(directory, {})

    def test_client_file_requires_desktop_type_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'client.json'
            file.write_text(json.dumps({'installed': {'client_id': 'client', 'client_secret': 'secret'}}))
            file.chmod(0o600)
            self.assertEqual(module.private_client(file)['client_id'], 'client')
            file.chmod(0o644)
            with self.assertRaises(ValueError):
                module.private_client(file)


if __name__ == '__main__':
    unittest.main()

