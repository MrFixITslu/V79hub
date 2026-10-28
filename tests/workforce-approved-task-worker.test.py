import ast,importlib.util,io,json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
spec=importlib.util.spec_from_file_location('worker',Path(__file__).parents[1]/'scripts/workforce-approved-task-worker.py')
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
class Response(io.BytesIO):status=200
class Opener:
 def __init__(self,body):self.body=body;self.calls=[]
 def open(self,request,timeout):self.calls.append(request);return Response(json.dumps(self.body).encode())
class WorkerTests(unittest.TestCase):
 def case(self,body):
  with tempfile.TemporaryDirectory() as directory:
   token=Path(directory)/'token';token.write_text('synthetic-test-worker-token-'+'0'*32);token.chmod(0o600)
   opener=Opener(body);result=w.run_once({'schema':1,'tokenFile':str(token)},opener)
   self.assertEqual(len(opener.calls),1);request=opener.calls[0]
   self.assertEqual(request.full_url,w.URL);self.assertEqual(request.data,b'{}');self.assertEqual(request.method,'POST')
   self.assertFalse(request.has_header('Origin'));self.assertNotIn('synthetic-test-worker-token',str(result))
   return result
 def test_idle(self):self.assertEqual(self.case({'job':None})['state'],'idle')
 def test_approved_work_item_result(self):self.assertEqual(self.case({'job':{'operation':'create_work_item','status':'succeeded','digest':'a'*64}})['state'],'succeeded')
 def test_release_response_rejected(self):
  with self.assertRaises(RuntimeError):self.case({'job':{'operation':'deploy_release','status':'succeeded','digest':'a'*64}})
 def test_unapproved_response_rejected(self):
  with self.assertRaises(RuntimeError):self.case({'job':{'operation':'create_work_item','status':'pending','digest':'a'*64}})
 def test_uncertain_result_latches_and_blocks_next_poll(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);config=root/'config.json';config.write_text('{}');config.chmod(0o600)
   with patch.object(w.sys,'argv',['worker',str(config)]),patch.object(w,'run_once',side_effect=RuntimeError('synthetic transport failure')) as execute,patch('sys.stdout',io.StringIO()):
    with self.assertRaises(SystemExit):w.main()
    self.assertTrue((root/'uncertain.json').exists())
    w.main();self.assertEqual(execute.call_count,1)
 def test_intent_is_durable_before_post_and_cleared_after_receipt(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);root.chmod(0o700)
   config=root/'config.json';config.write_text('{}');config.chmod(0o600)
   marker=root/'uncertain.json'
   def observe(_config):
    self.assertTrue(marker.is_file())
    self.assertEqual(json.loads(marker.read_text())['state'],'uncertain')
    return {'state':'idle','operation':'create_work_item'}
   with patch.object(w.sys,'argv',['worker',str(config)]),patch.object(w,'run_once',side_effect=observe) as execute,patch('sys.stdout',io.StringIO()):
    w.main()
   self.assertEqual(execute.call_count,1)
   self.assertFalse(marker.exists())
   self.assertEqual(json.loads((root/'status.json').read_text())['state'],'idle')
 def test_abrupt_process_exit_after_intent_fails_closed_without_replay(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);root.chmod(0o700)
   config=root/'config.json';config.write_text('{}');config.chmod(0o600)
   with patch.object(w.sys,'argv',['worker',str(config)]),patch.object(w,'run_once',side_effect=KeyboardInterrupt('synthetic kill')) as execute,patch('sys.stdout',io.StringIO()):
    with self.assertRaises(KeyboardInterrupt):w.main()
    self.assertTrue((root/'uncertain.json').exists())
    w.main()
   self.assertEqual(execute.call_count,1)
 def test_receipt_persist_failure_retains_intent_no_retry(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);root.chmod(0o700)
   config=root/'config.json';config.write_text('{}');config.chmod(0o600)
   with patch.object(w.sys,'argv',['worker',str(config)]),patch.object(w,'run_once',return_value={'state':'succeeded','operation':'create_work_item','approvedDigest':'a'*64}) as execute,patch.object(w.os,'replace',side_effect=OSError('disk unavailable')),patch('sys.stdout',io.StringIO()):
    with self.assertRaises(SystemExit):w.main()
    self.assertTrue((root/'uncertain.json').exists())
    w.main()
   self.assertEqual(execute.call_count,1)
 def test_embedded_installer_worker_matches_reviewed_source(self):
  root=Path(__file__).parents[1]
  src=(root/'scripts/workforce-approved-task-worker.py').read_text()
  tree=ast.parse((root/'scripts/workforce-install-approved-task-worker.py').read_text())
  literal=next(node.value for node in tree.body if isinstance(node,ast.Assign)
   and any(isinstance(target,ast.Name) and target.id=='WORKER_SOURCE' for target in node.targets))
  self.assertEqual(ast.literal_eval(literal),src)
 def test_redirect_refused(self):
  with self.assertRaises(RuntimeError):w.NoRedirect().redirect_request(None,None,None,None,None,None)
if __name__=='__main__':unittest.main()
