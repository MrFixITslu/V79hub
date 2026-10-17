"""The Hub UI builder must refuse backend/runtime dependency changes."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]/'scripts/marketing-production-panel-build.py'
spec = importlib.util.spec_from_file_location('ui_build', SOURCE)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class UiBuildTests(unittest.TestCase):
    def test_only_ui_operational_tests_and_dev_dependencies_are_allowed(self):
        package = {'dependencies': {'react': 'fixed'}, 'devDependencies': {}}
        lock = {'packages': {'': {}, 'node_modules/react': {'version': 'fixed'}, 'node_modules/test-dom': {'version': 'old', 'dev': True}}}
        new_package = copy.deepcopy(package)
        new_package['devDependencies']['test-dom'] = 'new'
        new_lock = copy.deepcopy(lock)
        new_lock['packages']['node_modules/test-dom']['version'] = 'new'
        build.verify_ui_scope(package, new_package, lock, new_lock, ['src/components/MarketingProductionPanel.tsx', 'tests/ui.test.mjs'])
        for path in ('server.ts', 'server/marketing-production-routes.mjs', 'Dockerfile', '.github/workflows/deploy.yml', 'src/components/OwnerAssistant.tsx'):
            with self.assertRaises(RuntimeError):
                build.verify_ui_scope(package, new_package, lock, new_lock, [path])
        bad = copy.deepcopy(new_package)
        bad['dependencies']['react'] = 'changed'
        with self.assertRaises(RuntimeError):
            build.verify_ui_scope(package, bad, lock, new_lock, ['package.json'])
        bad_lock = copy.deepcopy(new_lock)
        bad_lock['packages']['node_modules/react']['version'] = 'changed'
        with self.assertRaises(RuntimeError):
            build.verify_ui_scope(package, new_package, lock, bad_lock, ['package-lock.json'])

    def test_disposable_runner_sets_test_mode_without_changing_the_image(self):
        image = 'sha256:' + 'a' * 64
        command = build.isolated_test_command(image)
        self.assertEqual(command[:3], ['docker', 'run', '--rm'])
        self.assertEqual(command[command.index('--network')+1], 'none')
        self.assertIn('--read-only', command)
        self.assertEqual(command[command.index('--user')+1], 'node')
        self.assertIn('NODE_ENV=test', command)
        self.assertIn('NODE_OPTIONS=--import=./tests/isolated-env.mjs', command)
        self.assertEqual(command[command.index(image)+1], '--test')
        self.assertNotIn('--volume', command)
        self.assertNotIn('-v', command)
        self.assertNotIn('NODE_ENV=production', command)

    def test_existing_image_verification_is_non_deploying_and_writes_receipt_only_after_pass(self):
        for failure in (None, 'wrong-image', 'tests', 'live-drift'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                real_root = Path(directory)
                class PrivateRoot:
                    def is_dir(self): return True
                    def is_symlink(self): return False
                    def stat(self): return SimpleNamespace(st_uid=1000, st_mode=0o40700)
                    def __truediv__(self, name): return real_root/name
                calls = []
                image = 'sha256:ac3f3262476deeba190a362a6782e02836fff2a7d701ab219a60be7f8caaba0e'
                metadata = {'Id': image, 'Config': {'Labels': {'org.opencontainers.image.revision': build.COMMIT}, 'Env': ['NODE_ENV=production']}}
                if failure == 'wrong-image': metadata['Id'] = 'different'
                def runner(args, **kwargs):
                    calls.append(args)
                    if args[:3] == ['docker', 'image', 'inspect']: return json.dumps([metadata]).encode()
                    if args[:2] == ['docker', 'run']:
                        if failure == 'tests': raise RuntimeError('synthetic failed test run')
                        return b''
                    if args[:2] == ['docker', 'exec']: return b'{"signedLedgerVerified":true,"approvedBrandHasLogo":false}'
                    raise AssertionError('Unexpected command: ' + repr(args))
                snapshots = [{'id': 'unchanged'}, {'id': 'changed' if failure == 'live-drift' else 'unchanged'}]
                with patch.object(build, 'Path', return_value=PrivateRoot()), \
                     patch.object(build.socket, 'gethostname', return_value='v79sl'), \
                     patch.object(build.os, 'getuid', return_value=1000), \
                     patch.object(build.pwd, 'getpwuid', return_value=SimpleNamespace(pw_name='firelion')), \
                     patch.object(build, 'snapshot', side_effect=snapshots), \
                     patch.object(build, 'verify_checkout_scope') as verify_scope, \
                     patch.object(build, 'run', side_effect=runner):
                    if failure:
                        with self.assertRaises(RuntimeError): build.verify_existing()
                    else: build.verify_existing()
                    verify_scope.assert_called_once_with(real_root/'V79hub')
                receipt = real_root/'ui-build-receipt.json'
                self.assertEqual(receipt.exists(), failure is None)
                self.assertFalse(any('build' in args or 'compose' in args for args in calls))
                self.assertEqual(metadata['Config']['Env'], ['NODE_ENV=production'])
                if failure is None:
                    record = json.loads(receipt.read_text())
                    self.assertEqual(record['candidate']['image'], image)
                    self.assertTrue(record['isolatedTestsPassed'])
                    self.assertTrue(record['reusedExistingImage'])
                    self.assertFalse(record['deploymentPerformed'])
                    self.assertEqual(record['testEnvironment'], 'test')

    def test_logo_probe_verifies_signature_and_emits_only_metadata(self):
        harness = r'''
const vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const businessId='44289786-2583-4bf1-9db2-99eca95dfd96',key='k'.repeat(64);
const state={configRevision:1,brand:{logoPng:'PRIVATE_LOGO_BYTES',name:'PRIVATE_BRAND'},jobs:[{id:'job',status:'awaiting_owner',angle:'PRIVATE_ANGLE',bundle:{brand:{logoPng:null},review:{warnings:['Text wordmark used; original brand logo has not been supplied']}}}]};
const canonical=v=>JSON.stringify(v,(_k,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
let hmac=crypto.createHmac('sha256',key).update('v79-marketing-production-v1\n'+businessId+'\n'+canonical(state)).digest('hex'),closed=false,out=[];
class FakeDb{constructor(_path,options){assert.deepEqual(JSON.parse(JSON.stringify(options)),{readonly:true,fileMustExist:true});}pragma(value){assert.equal(value,'query_only=ON');}prepare(sql){assert.equal(sql,'SELECT envelope FROM marketing_production_state WHERE business_id=?');return{get(id){assert.equal(id,businessId);return {envelope:JSON.stringify({state,hmac})};}};}close(){closed=true;}}
const requireFake=name=>name==='better-sqlite3'?FakeDb:require(name);
const run=()=>vm.runInNewContext(PROBE,{require:requireFake,process:{env:{V79_MARKETING_PRODUCTION_AUDIT_KEY:key}},Buffer,console:{log(v){out.push(v);}}});
run();assert.ok(closed);const result=JSON.parse(out[0]);assert.equal(result.approvedBrandHasLogo,true);assert.equal(result.packages[0].renderedBrandHasLogo,false);
assert.ok(!out[0].includes('PRIVATE_'));hmac='0'.repeat(64);closed=false;out=[];assert.throws(run,/Ledger integrity/);assert.ok(closed);assert.deepEqual(out,[]);
'''
        program = 'const PROBE=' + json.dumps(build.LOGO_PROBE) + ';\n' + harness
        result = subprocess.run(['node', '--input-type=commonjs', '-'], input=program.encode(), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
