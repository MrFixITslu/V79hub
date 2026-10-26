#!/usr/bin/env python3
"""Offline guards for read-only V8 inventory and still-explicit encrypted capture."""
import ast
import base64
from pathlib import Path
import re
import unittest

SOURCE = Path(__file__).parents[1]/'scripts/capture-post-v8-encrypted-checkpoint.py'
PINNED={
    'v79-hub': ('e02a3b4b40c521257582c1456acb5f9f3949dd22d9b1145de3c2aec77d3aba5c','sha256:66caa099adf1321b72a90b22f8125981e5a6d99b5920cebae0454541cccd9fa7'),
    'v79-tiquet-manager': ('2ab5154f800733e4e090ab40f4d16f0c6b054986fd013b7483b8b1d2937ce982','sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0'),
    'v79-business-agent': ('b7e559c1cdd6ca73ad4625c94ce39334558f3ae891dd4bc7accfd9ed7a478d28','sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b'),
    'v79-hub-postgres': ('5b97b804ed9590a0fd54e86f4a610aae5200131f956549189b0e4aeeab1ec75c','sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24'),
    'tiquet-postgres': ('8e4d1093faf710f555795a70caf57b67da8dc71b29555ee0d681c5c47e3b1140','sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685')
}
def module_contents():
    text=SOURCE.read_text()
    raw=next(ast.literal_eval(n.value) for n in ast.parse(text).body
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READINESS_B64' for t in n.targets))
    decoded=base64.b64decode(raw,validate=True).decode()
    ast.parse(decoded)
    return text,decoded

class TestPostV8Recovery(unittest.TestCase):
    def test_verified_v8_images_and_container_ids(self):
        _,probe=module_contents()
        for name,(container_id,image) in PINNED.items():
            self.assertIn(repr(name)+': '+repr(container_id),probe)
            self.assertIn(repr(name)+': '+repr(image),probe)
        self.assertIn("o['Id']==EXPECTED_IDS[name]",probe)
        self.assertNotIn('sha256:d722f357206fec938eca691c92ddfe57ece62811f62124f6fbf760258b2b6940',probe)

    def test_exact_sealed_composes_and_mounts(self):
        _,probe=module_contents()
        self.assertIn('manifest-v79-hub-candidate.json',probe)
        self.assertIn('e785277a3970476c214fade92763fac7a41a9151ece7365c67c8cb2b439023c6',probe)
        self.assertIn('manifest-v79-tiquet-manager-candidate.json',probe)
        self.assertIn('e8f21d2c797c5f8edf012ba47d9122b8ed142b7256282204925ec071c19c9010',probe)
        self.assertIn('FINAL_HUB_COMPOSE_CHAIN_DIFFERS',probe)
        self.assertIn('FINAL_TIQUET_COMPOSE_CHAIN_DIFFERS',probe)
        self.assertIn('FINAL_APPLICATION_MOUNT_SCOPE_DIFFERS',probe)
        self.assertIn("report['mount_count']=sum(len(v) for v in EXPECTED_MOUNTS.values())",probe)
        self.assertIn("not p.is_symlink",probe)

    def test_verified_v8_inventory_bound_before_app_shutdown(self):
        runner,_=module_contents()
        self.assertIn("report=preflight_capture()",runner)
        self.assertIn("INVENTORY=report['inventory_sha256']",runner)
        self.assertIn("pin_file=run/'inventory-sha256'",runner)
        self.assertIn("need(report['inventory_sha256']==INVENTORY",runner)
        self.assertIn("READINESS_CHANGED_NO_PAUSE",runner)
        self.assertIn("OFFHOST_CAPTURE_POINTER_UNBOUND",runner)
        self.assertIn("INVENTORY=pointer.get('inventory_sha256')",runner)
        self.assertIn("CAPTURE_AND_RESTORE=NOT_RUN",base64.b64decode(
           next(ast.literal_eval(n.value) for n in ast.parse(runner).body
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READINESS_B64' for t in n.targets))
          ).decode())

    def test_backup_stays_encrypted_offhost_and_apps_resume(self):
        runner,_=module_contents()
        for s in (
            "encrypt_args(keyring)", "encrypted_stream(['docker','save'",
            "'--encrypt','--recipient',RECIPIENT", "pg_dump", "OFFHOST_CIPHERTEXT_AND_DECRYPT=PASS_15_OF_15",
            "resume_server", "restore_originals(journal,paused)",
            "if paused:", "signal.signal(signal.SIGTERM",
            "CAPTURE_INTERRUPTED", "OTHER_DATABASE_CLIENT_REQUIRES_REVIEW",
            "'restore_tested':False", "NEW_CAPTURE_RESTORE_REHEARSED=FALSE",
            "'--preflight'", "'--capture'"
        ): self.assertIn(s,runner)
        self.assertNotIn("docker','rm'",runner)
        self.assertNotIn("'--force-recreate'",runner)

if __name__=='__main__':
    unittest.main()
