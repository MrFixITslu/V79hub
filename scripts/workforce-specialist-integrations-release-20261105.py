#!/usr/bin/env python3
"""Scoped specialist integrations rollout. Preserves the complete existing runtime profile."""
import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('paired_guard',Path(__file__).with_name('workforce-specialist-guarded-release.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.APP_SHA='02c9d24c06593c2309361ff385149e78a8c46dc5'
m.ROOT=Path('/home/firelion/.v79-specialist-integrations-02c9d24')
m.SPECS={'v79-business-agent': {'old': 'sha256:68c842ac972cc8bc2340c4ea5413f15c18f0941f7e8247c138b89a050e0383fb', 'tag': 'localhost/v79-specialist-agent:02c9d24', 'stage': 'v79-specialist-agent-stage-02c9d24', 'previous': 'v79-specialist-agent-rollback-02c9d24', 'mounts': 1, 'url': 'https://hub.v79sl.com/', 'flags': {}}, 'v79-hub': {'old': 'sha256:19450047c72f77c1d207f0046d6fd5123e34ed3fc74600b16b76ed74e81ba86f', 'tag': 'localhost/v79-specialist-hub:02c9d24', 'stage': 'v79-specialist-hub-stage-02c9d24', 'previous': 'v79-specialist-hub-rollback-02c9d24', 'mounts': 7, 'url': 'https://hub.v79sl.com/', 'flags': {}}}
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
