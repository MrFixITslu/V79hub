#!/usr/bin/env python3
"""Synthetic regression checks for recovery-only baseline; never uses Docker."""
import copy
import importlib.util
from pathlib import Path
from unittest import mock

file=Path(__file__).resolve().parents[1]/'scripts/portfolio-remaining-recovery-baseline.py'
spec=importlib.util.spec_from_file_location('v79_recovery_baseline',file)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

base={'config':{'Cmd':['node','server.js']},
      'env':{'SESSION':'DO_NOT_PRINT'},'mounts':[],'networks':['proxy'],
      'host':{'Dns':[],'DnsOptions':[],'DnsSearch':[],'Privileged':False}}
restored=copy.deepcopy(base)
for key in r.DNS_FIELDS:restored['host'][key]=None
assert r.dns_only_equivalent(base,restored)
assert r.dns_only_equivalent(restored,base)
assert r.dns_only_equivalent(base,base)
for k in r.DNS_FIELDS:
    negative=copy.deepcopy(restored);negative['host'][k]=['invalid.test']
    assert not r.dns_only_equivalent(base,negative)
negative=copy.deepcopy(restored);negative['host']['Privileged']=True
assert not r.dns_only_equivalent(base,negative)
negative=copy.deepcopy(restored);negative['env']['SESSION']='NEW_SECRET'
assert not r.dns_only_equivalent(base,negative)
negative=copy.deepcopy(restored);negative['networks']=['other']
assert not r.dns_only_equivalent(base,negative)
negative=copy.deepcopy(restored);negative['mounts']=[{'Destination':'/other'}]
assert not r.dns_only_equivalent(base,negative)
negative=copy.deepcopy(restored);negative['config']['Cmd']=['node','wrong.js']
assert not r.dns_only_equivalent(base,negative)
assert 'DO_NOT_PRINT' not in str(r.dns_only_equivalent(base,restored))
# A successful private baseline MUST have a status that is never accepted by the
# existing switch helper (which requires PLAN_PREPARED_NOT_DEPLOYED).
src=file.read_text()
assert "'RECOVERY_BASELINE_PREPARED_NOT_DEPLOYABLE'" in src
assert "deployment_authorization':'NO'" in src
assert "r.validate_storage_and_networks(rendered,rendered_service,row)" in src
assert "labels.get('com.docker.compose.project.config_files')" in src
assert "check_shared(r)" in src
assert "current_runtime_container_ids" in src
assert "CHECKPOINT_CIPHERTEXT_CHANGED" in src
assert "R1_CUSTOMER_RELEASE','NO_GO" in src
r.test()
print('RECOVERY_REPLAN_NEGATIVE_CASES=PASS')
