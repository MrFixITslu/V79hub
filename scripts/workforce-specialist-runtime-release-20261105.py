#!/usr/bin/env python3
"""Agent-only performance follow-up, using the unchanged paired guard and recovery proof."""
import importlib.util,copy,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('paired_guard',Path(__file__).with_name('workforce-specialist-guarded-release.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.APP_SHA='459c542fa37103fc8b97c3c26d6f67fc932e3602'
m.ROOT=Path('/home/firelion/.v79-workforce-runtime-459c542')
m.SPECS={'v79-business-agent':{'old':'sha256:9d5843b1951e3c5ce12f9dcf6414dfe0d032fc224f0a1a9ad4814e43a5ddfd9b','tag':'localhost/v79-workforce-agent:459c542','stage':'v79-agent-runtime-stage-459c542','previous':'v79-agent-runtime-rollback-459c542','mounts':1,'url':'https://hub.v79sl.com/','flags':{'OLLAMA_AGENT_MODEL':'qwen2.5:3b','V79_SPECIALIST_REVIEW_MODEL':'qwen2.5:3b'}}}
profile={'OLLAMA_NUM_THREADS':'2','OLLAMA_USE_MMAP':'0','OLLAMA_CONTEXT_SIZE':'3072'}
original_expected=m.expected_runtime
def expected_runtime(original,spec):
 result=original_expected(original,spec)
 result['Config']['Env']=[v for v in result['Config']['Env'] if v.split('=',1)[0] not in profile]+[k+'='+v for k,v in profile.items()]
 return result
m.expected_runtime=expected_runtime
m.TIMERS.append('v79-specialist-review.timer')
original_pause=m.pause_timers
def pause_timers(doc):
 original_pause(doc)
 for _ in range(45):
  state=m.systemctl('show','v79-specialist-review.service','-p','ActiveState','--value').stdout.strip()
  if state not in ('active','activating','deactivating'):return
  time.sleep(1)
 raise RuntimeError('Specialist worker did not drain')
m.pause_timers=pause_timers
if __name__=='__main__':
 m.ROOT.mkdir(mode=0o700,exist_ok=True)
 previous=Path('/home/firelion/.v79-workforce-delivery-release-20261105')
 for name in ['offhost-restore-receipt.json','V79_Workforce_PreRelease_Encrypted_20261105.tar.gz.gpg']:
  target=m.ROOT/name
  if not target.exists():target.symlink_to(previous/name)
 m.main()
