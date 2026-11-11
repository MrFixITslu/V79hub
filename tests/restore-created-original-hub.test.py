#!/usr/bin/env python3
"""Real Node HTTP checks and finish-only ordering; no production access."""
import contextlib
import http.server
import importlib.util
import json
from pathlib import Path
import subprocess
import threading
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('recovery',Path(__file__).parents[1]/'scripts/restore-created-original-hub.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class Recovery(unittest.TestCase):
    def test_real_node_http_requires_exact_status_and_body(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                code,status=(200,'ok') if self.path=='/ok' else (503,'ok') if self.path=='/503' else (200,'wrong')
                self.send_response(code);self.end_headers();self.wfile.write(json.dumps({'status':status}).encode())
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            for path,expected in (('/ok',0),('/503',2),('/wrong',2)):
                result=subprocess.run(['node','-e',m.health_script(server.server_port,path,'ok')],capture_output=True,timeout=10)
                self.assertEqual(result.returncode,expected)
                self.assertEqual(json.loads(result.stdout)['http'],503 if path=='/503' else 200)
        finally:server.shutdown();server.server_close();worker.join()

    def fake(self,wrong_tiquet=False):
        actions=[]
        rows={name:{'Id':name+'-exact','Image':name+'-original','State':{'Running':True,'Status':'running','Health':{'Status':'healthy'}},
             'Config':{'ExposedPorts':{str(port)+'/tcp':{}}}} for name,port in (('v79-hub',3040),('v79-tiquet-manager',3050))}
        plan={'apps':{name:{'baseline':row,'rollback_image':{'Id':row['Image']}} for name,row in rows.items()}}
        backend=types.SimpleNamespace(inspect=lambda name,**kw:rows[name] if name in rows else next(r for r in rows.values() if r['Id']==name),
            protected=lambda:actions.append('protected'),check_files=lambda:actions.append('files'))
        transaction=types.SimpleNamespace(protected_fingerprint=lambda row:json.dumps(row,sort_keys=True))
        journal=[{'event':e,'app':a} for e,a in [('TIMERS_PAUSE_INTENT',None),('CANDIDATE_INTENT','v79-hub'),
            ('CANDIDATE_FAILED','v79-hub'),('ROLLBACK_INTENT','v79-hub'),('ROLLBACK_FAILED','v79-hub'),
            ('ROLLBACK_INCOMPLETE',None),('TIMERS_HELD_OPERATOR_REVIEW_REQUIRED',None)]]
        files={'outcome.json':json.dumps({'reason':'ROLLBACK_INCOMPLETE_OPERATOR_REQUIRED','release_decision':'HOLD','status':'BLOCKED'}).encode(),
            'exit-code':b'0','events.jsonl':b'\n'.join(json.dumps(e).encode() for e in journal)}
        def call(args):
            if args[:2]==['systemctl','--user']:return b'inactive'
            if args[:2]==['docker','exec']:
                name='v79-hub' if args[2]==rows['v79-hub']['Id'] else 'v79-tiquet-manager';actions.append('http-'+name)
                return json.dumps({'http':200,'status':'wrong' if wrong_tiquet and name!='v79-hub' else 'ok' if name=='v79-hub' else 'healthy'}).encode()
            self.fail('Unexpected mutation command '+repr(args))
        original=types.SimpleNamespace(private_file=lambda path:files[path.name],release_lock=contextlib.nullcontext,TIMERS=['one.timer','two.timer','three.timer'],
            call=call,timers_resume=lambda:actions.append('resume-timers'),write_new=lambda *args:actions.append('receipt'),safe_reason=lambda e:str(e))
        helper=types.SimpleNamespace(validate=lambda args:(None,original,transaction,plan,backend))
        return helper,actions,rows

    def test_finish_running_never_starts_container_and_resumes_only_after_two_http_checks(self):
        helper,actions,_=self.fake()
        with patch.object(m,'checked_entry'):
            result=m.restore(helper,finish_running=True)
        self.assertTrue(result['status'].startswith('PASS_'));self.assertFalse(result['hub_start_requested'])
        self.assertLess(actions.index('http-v79-tiquet-manager'),actions.index('resume-timers'))
        self.assertFalse(result['containers_recreated']);self.assertFalse(result['host_port_changes_made'])

    def test_bad_internal_http_keeps_timers_held(self):
        helper,actions,_=self.fake(wrong_tiquet=True)
        with patch.object(m,'checked_entry'):result=m.restore(helper,finish_running=True)
        self.assertEqual(result['status'],'BLOCKED');self.assertNotIn('resume-timers',actions)

    def test_unhealthy_running_hub_does_not_start_or_resume(self):
        helper,actions,rows=self.fake();rows['v79-hub']['State']['Health']['Status']='unhealthy'
        with patch.object(m,'checked_entry'):result=m.restore(helper,finish_running=True)
        self.assertEqual(result['status'],'BLOCKED');self.assertNotIn('resume-timers',actions)
        self.assertFalse(any(a.startswith('http-') for a in actions))


if __name__=='__main__':unittest.main()
