"""Offline scope/redaction checks; never calls SSH or Docker."""
import ast
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'scripts/p1-installed-security-readonly.py'
spec=importlib.util.spec_from_file_location('reader',PATH)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReaderTests(unittest.TestCase):
    def test_fixed_public_scope(self):
        with redirect_stdout(io.StringIO()):r.self_test()
        self.assertEqual(set(r.EXPECTED),{'v79-hub','v79-tiquet-manager'})
        self.assertNotIn('process.env',r.NODE_HASH)
        self.assertNotIn('fetch(',r.NODE_HASH)

    def test_output_cannot_emit_secret_values(self):
        output=io.StringIO()
        with redirect_stdout(output):
            with self.assertRaises(r.Stop):r.emit('ENV','PRIVATE_MARKER')
        self.assertNotIn('PRIVATE',output.getvalue())

    def test_inspection_failure_never_means_absence(self):
        with patch.object(r,'docker',side_effect=r.Stop('DOCKER_FAILED')):
            with self.assertRaisesRegex(r.Stop,'DOCKER_FAILED'):r.inspect('v79-hub')

    def test_no_mutating_docker_or_database_commands(self):
        tree=ast.parse(PATH.read_text())
        lists=[node for node in ast.walk(tree) if isinstance(node,ast.List)]
        commands=[[x.value for x in node.elts if isinstance(x,ast.Constant) and isinstance(x.value,str)] for node in lists]
        for command in commands:
            self.assertFalse(set(command)&{'rm','prune','start','stop','restart','create','run','compose','up','psql','gpg','systemctl'})
        self.assertIn(['container','inspect'],commands)
        self.assertTrue(any(command[:3]==['exec','node','-e'] for command in commands))

if __name__=='__main__':unittest.main()
