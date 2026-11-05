#!/usr/bin/env python3
"""Hub-only evidence controls release; retains prior tested recovery and original container."""
import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('paired_guard',Path(__file__).with_name('workforce-specialist-guarded-release.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.APP_SHA='2be09c733ba57eed1648a14e9296a94a26b17e43'
m.ROOT=Path('/home/firelion/.v79-task-evidence-cutover-2be09c7')
m.SPECS={'v79-hub':{'old':'sha256:29d1158c36c4a3f92b4c682bc1f01a20af5e2e49280c01a950d9a3d9a75f609f','tag':'localhost/v79-task-evidence-hub:2be09c7','stage':'v79-task-evidence-stage-2be09c7','previous':'v79-task-evidence-rollback-2be09c7','mounts':7,'url':'https://hub.v79sl.com/','flags':{}}}
m.TIMERS+=['v79-specialist-review.timer','v79-sentinel-workforce-relay.timer']
original_pause=m.pause_timers
def pause_timers(doc):
 original_pause(doc)
 for service in ['v79-specialist-review.service','v79-sentinel-workforce-relay.service']:
  for _ in range(45):
   state=m.systemctl('show',service,'-p','ActiveState','--value').stdout.strip()
   if state not in ('active','activating','deactivating'):break
   time.sleep(1)
  else:raise RuntimeError('Existing worker did not drain')
m.pause_timers=pause_timers
if __name__=='__main__':
 m.ROOT.mkdir(mode=0o700,exist_ok=True)
 previous=Path('/home/firelion/.v79-workforce-delivery-release-20261105')
 for name in ['offhost-restore-receipt.json','V79_Workforce_PreRelease_Encrypted_20261105.tar.gz.gpg']:
  target=m.ROOT/name
  if not target.exists():target.symlink_to(previous/name)
 m.main()
