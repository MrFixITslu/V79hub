#!/usr/bin/env python3
"""Scoped specialist integrations rollout. Preserves the complete existing runtime profile."""
import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('paired_guard',Path(__file__).with_name('workforce-specialist-guarded-release.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.APP_SHA='4fe76558b3aca9a81f548b59bc21b489f0a3805d'
m.ROOT=Path('/home/firelion/.v79-gateway-origin-fix-4fe7655')
m.SPECS={'v79-hub': {'old': 'sha256:b9b9a2c9377780c8b615b508053ee93f09fb3dfb55129b3c4f50dbd17c8e41b7', 'tag': 'localhost/v79-gateway-hub:4fe7655', 'stage': 'v79-gateway-origin-stage-4fe7655', 'previous': 'v79-gateway-origin-rollback-4fe7655', 'mounts': 7, 'url': 'https://hub.v79sl.com/', 'flags': {}}}
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
