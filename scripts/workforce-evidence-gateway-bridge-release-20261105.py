#!/usr/bin/env python3
"""Scoped specialist integrations rollout. Preserves the complete existing runtime profile."""
import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('paired_guard',Path(__file__).with_name('workforce-specialist-guarded-release.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.APP_SHA='455ad532711f9827721d9abec748f36de4c7437f'
m.ROOT=Path('/home/firelion/.v79-gateway-hub-bridge-455ad53')
m.SPECS={'v79-business-agent': {'old': 'sha256:d12fd58bde5e0892b02e59b3031d057ef9f4c6fa665696148c6b55a6fa43dbf9', 'tag': 'localhost/v79-gateway-agent:455ad53', 'stage': 'v79-specialist-agent-gateway-stage-455ad53', 'previous': 'v79-specialist-agent-gateway-rollback-455ad53', 'mounts': 1, 'url': 'https://hub.v79sl.com/', 'flags': {}}, 'v79-hub': {'old': 'sha256:1b7ecf768b7e873a65d26c291ffe1b3e979ea02e89c005795e7684b1e212760b', 'tag': 'localhost/v79-gateway-hub:455ad53', 'stage': 'v79-specialist-hub-gateway-stage-455ad53', 'previous': 'v79-specialist-hub-gateway-rollback-455ad53', 'mounts': 7, 'url': 'https://hub.v79sl.com/', 'flags': {}}}
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
