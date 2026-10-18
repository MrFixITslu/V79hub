"""Offline runner wiring tests. Does not operate Docker."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
r=load('runner','scripts/portfolio-isolated-academy-startup.py')
t=load('fixtures','tests/academy-isolation-contract.test.py')

class WiringTests(unittest.TestCase):
    def setUp(self):
        r.PUBLIC_ENV=t.PUBLIC.copy()
        r.EXPECTED_CONFIG={'Cmd':['node','dist/server.cjs'],'Entrypoint':['docker-entrypoint.sh'],'WorkingDir':'/app'}

    def fixture(self,state='created'):
        row=t.fixture(state);row['Config'].update(r.EXPECTED_CONFIG)
        row['Config']['Healthcheck']={'Test':['NONE']};row['Id']='b'*64
        return row

    def test_embedded_pure_contract_is_exact_source_copy(self):
        source=(ROOT/'scripts/academy-isolation-contract.py').read_text()
        runner=(ROOT/'scripts/portfolio-isolated-academy-startup.py').read_text()
        embedded=runner.split('# BEGIN PURE CONTRACT (byte-compared by CI; standalone source-pinned helper)\n',1)[1].split('# END PURE CONTRACT',1)[0]
        self.assertEqual(embedded,source[source.index('OWNER ='):])

    def test_created_and_running_pass_but_running_without_mounts_fails(self):
        self.assertTrue(r.isolated(self.fixture(),t.IMAGE,t.TOKEN))
        row=self.fixture('running');self.assertTrue(r.isolated(row,t.IMAGE,t.TOKEN))
        row['Mounts']=[];self.assertFalse(r.isolated(row,t.IMAGE,t.TOKEN))

    def test_command_and_healthcheck_drift_rejected(self):
        for field,value in [('Cmd',['sh']),('Entrypoint',['sh']),('WorkingDir','/'),('Healthcheck',{'Test':['CMD','true']})]:
            row=self.fixture();row['Config'][field]=value
            self.assertFalse(r.isolated(row,t.IMAGE,t.TOKEN))

    def test_inspect_failure_is_not_absence_when_listing_fails(self):
        with patch.object(r,'command',return_value=SimpleNamespace(returncode=1,stdout=b'')):
            with self.assertRaisesRegex(r.Stop,'ABSENCE_QUERY_FAILED'):r.inspect('container','b'*64)

    def test_inspect_failure_is_not_absence_when_exact_resource_listed(self):
        with patch.object(r,'command',side_effect=[SimpleNamespace(returncode=1),SimpleNamespace(returncode=0,stdout=('b'*64+'|probe\n').encode())]):
            with self.assertRaisesRegex(r.Stop,'CONTAINER_INSPECT_FAILED'):r.inspect('container','b'*64)

    def test_cleanup_uses_verified_immutable_id_not_name(self):
        row=self.fixture()
        with patch.object(r,'inspect',side_effect=[row,None]),patch.object(r,'command',return_value=SimpleNamespace(returncode=0)) as command:
            self.assertTrue(r.cleanup(row['Name'],t.TOKEN,t.IMAGE,row['Id']))
        self.assertEqual(command.call_args.args[0],['docker','rm','-f',row['Id']])

    def test_cleanup_refuses_different_id(self):
        row=self.fixture();row['Id']='c'*64
        with patch.object(r,'inspect',return_value=row),patch.object(r,'command') as command:
            with self.assertRaisesRegex(r.Stop,'FOREIGN_RESOURCE'):r.cleanup('probe',t.TOKEN,t.IMAGE,'b'*64)
            command.assert_not_called()

    def test_primary_and_cleanup_failures_still_check_production(self):
        with patch.object(r,'inspect',return_value=None),patch.object(r,'secrets') as secrets, \
             patch.object(r,'command',return_value=SimpleNamespace(returncode=0,stdout=('b'*64).encode())), \
             patch.object(r,'isolated',return_value=False),patch.object(r,'cleanup',side_effect=r.Stop('CLEANUP_FAILED')), \
             patch.object(r,'verify_production') as verify,patch.object(r,'emit') as emit:
            secrets.token_hex.return_value=t.TOKEN
            with self.assertRaisesRegex(r.Stop,'CLEANUP_FAILED'):r.exercise_probe(None,{},t.IMAGE)
            verify.assert_called_once()
            self.assertIn(('STOP','PRIMARY_ISOLATION_NOT_PROVEN'),[x.args for x in emit.call_args_list])

    def test_create_failure_checks_production_without_guessing_cleanup_target(self):
        with patch.object(r,'inspect',return_value=None), \
             patch.object(r,'command',return_value=SimpleNamespace(returncode=1,stdout=b'')), \
             patch.object(r,'cleanup') as cleanup,patch.object(r,'verify_production') as verify,patch.object(r,'emit'):
            with self.assertRaisesRegex(r.Stop,'ACADEMY_CREATE_FAILED'):r.exercise_probe(None,{},t.IMAGE)
            cleanup.assert_not_called();verify.assert_called_once()

    def test_exited_state_is_cleanup_only(self):
        row=self.fixture('running');row['State'].update(Status='exited',Running=False)
        self.assertFalse(r.isolated(row,t.IMAGE,t.TOKEN))
        self.assertTrue(r.isolated(row,t.IMAGE,t.TOKEN,cleanup_mode=True))

if __name__=='__main__':unittest.main()
