#!/usr/bin/env python3
"""Scoped specialist integrations rollout. Preserves the complete existing runtime profile."""
import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('paired_guard',Path(__file__).with_name('workforce-specialist-guarded-release.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.APP_SHA='0f8e7ff3cc5a1560400004cf0eddffc38156c638'
m.ROOT=Path('/home/firelion/.v79-gateway-callback-fix-0f8e7ff')
m.SPECS={'v79-hub': {'old': 'sha256:3ddba0efb6fa913fcd7c4295119902581219166db333c7de15fa9b4de2fcaced', 'tag': 'localhost/v79-gateway-hub:0f8e7ff', 'stage': 'v79-gateway-callback-stage-0f8e7ff', 'previous': 'v79-gateway-callback-rollback-0f8e7ff', 'mounts': 7, 'url': 'https://hub.v79sl.com/', 'flags': {}}}
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
