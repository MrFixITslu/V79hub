#!/usr/bin/env python3
"""Format audit only. No extraction, container commands, image import or restore."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import tarfile

APPS=('v79-hub','v79-tiquet-manager')
DBS=('v79-hub-postgres','tiquet-postgres')
ROOT=Path.home()/'V79-Portfolio-Checkpoints/p1-interrupted-t3TEQV5N.qmLDzVUD'
MAX_SMALL=32*1024*1024
class Stop(Exception):pass
def need(ok,code):
    if not ok:raise Stop(code)
def safe_name(name):
    need(isinstance(name,str) and name and not name.startswith('/') and '\\' not in name and '\x00' not in name and '..' not in PurePosixPath(name).parts,'ARCHIVE_PATH_UNSAFE')
    return name.removeprefix('./').rstrip('/')
def json_object(raw):
    def pairs(items):
        result={}
        for k,v in items:
            need(k not in result,'JSON_DUPLICATE_KEY');result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=pairs)
@contextlib.contextmanager
def decrypted(path):
    child=subprocess.Popen(['gpg','--batch','--quiet','--decrypt',str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    try:
        yield child.stdout
        # Consume padding/trailer to verify GPG authentication even if tar stops early.
        while child.stdout.read(131072):pass
        child.stdout.close()
        need(child.wait(timeout=30)==0,'GPG_STREAM_FAILED')
    finally:
        if child.stdout and not child.stdout.closed:child.stdout.close()
        if child.poll() is None:child.kill()
        child.wait()
def entries(stream,limit=30000):
    seen=set()
    with tarfile.open(fileobj=stream,mode='r|') as archive:
        for member in archive:
            name=safe_name(member.name)
            need(name and name not in seen,'ARCHIVE_DUPLICATE_PATH')
            seen.add(name);need(len(seen)<=limit,'ARCHIVE_MEMBER_LIMIT')
            need(member.isfile() or member.isdir(),'ARCHIVE_LINK_OR_SPECIAL_ENTRY')
            need(not member.mode & 0o7000,'ARCHIVE_PRIVILEGED_MODE')
            need(0<=member.size<=4*1024**3,'ARCHIVE_SIZE_LIMIT')
            yield name,member,archive

def configuration(stream):
    files={};total=0
    for name,m,a in entries(stream,100):
        need(m.isfile(),'CONFIG_NONREGULAR_ENTRY')
        total+=m.size;need(total<=MAX_SMALL,'CONFIG_RAM_LIMIT')
        f=a.extractfile(m);raw=f.read(m.size+1)
        need(len(raw)==m.size,'CONFIG_TRUNCATED');files[name]=raw
    need({'runtime.json','frozen-compose.json','input-map.json'}<=set(files),'CONFIG_RECORD_MISSING')
    rows=json_object(files['runtime.json']);models=json_object(files['frozen-compose.json']);inputs=json_object(files['input-map.json'])
    need(isinstance(rows,dict) and set(rows)==set(APPS+DBS),'RUNTIME_ROLES_INVALID')
    need(isinstance(models,dict) and set(models)==set(APPS),'FROZEN_MODELS_INVALID')
    need(isinstance(inputs,dict) and all(re.fullmatch(r'[0-9]+',k) and isinstance(v,str) and v.startswith('/') and '..' not in PurePosixPath(v).parts for k,v in inputs.items()),'CONFIG_INPUT_MAP_INVALID')
    need(set(files)=={'runtime.json','frozen-compose.json','input-map.json'}|{'config/'+k for k in inputs},'CONFIG_RECORD_SET_INVALID')
    ids=set()
    for name,row in rows.items():
        need(isinstance(row,dict) and row.get('Name')=='/'+name and re.fullmatch(r'[a-f0-9]{64}',row.get('Id','')) and re.fullmatch(r'sha256:[a-f0-9]{64}',row.get('Image','')),'RUNTIME_IDENTITY_INVALID')
        ids.add(row['Id'])
    need(len(ids)==4,'RUNTIME_IDS_NOT_UNIQUE')
    need(rows[DBS[0]]['Image']=='sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24' and rows[DBS[1]]['Image']=='sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685','DATABASE_IMAGE_CHANGED')
    return rows

def mapping(rows):
    result={};counts={'v79-hub':6,'v79-tiquet-manager':2}
    allowed={'v79-hub':{'/app/data','/app/logs','/run/secrets/v79-agent-token','/run/secrets/v79-workforce-token','/run/secrets/v79-readonly-platform-token','/run/secrets/v79-coo-github-token','/run/v79-workforce-reports'},'v79-tiquet-manager':{'/app/data','/app/uploads'}}
    for role in APPS:
        mounts=rows[role].get('Mounts');need(isinstance(mounts,list) and len(mounts)==counts[role],'MOUNT_COUNT_CHANGED')
        targets=set()
        for i,m in enumerate(mounts):
            dest=m.get('Destination');need(dest in allowed[role] and dest not in targets and m.get('Type') in ('bind','volume'),'MOUNT_MAPPING_INVALID')
            targets.add(dest);result[f'{role}-mount-{i}.tar.gpg']=dest
        need('/app/data' in targets,'APP_DATA_MOUNT_MISSING')
    return result

def mount_archive(stream,destination):
    # docker cp emits basename roots (not the full absolute container path).
    prefix=PurePosixPath(destination).name;count=0;total=0
    for name,m,a in entries(stream):
        need(name==prefix or name.startswith(prefix+'/'),'MOUNT_ARCHIVE_ROOT_MISMATCH')
        total+=m.size;need(total<=512*1024**2,'MOUNT_BYTES_LIMIT')
        if name==prefix:need(m.isdir() if destination in ('/app/data','/app/uploads','/app/logs','/run/v79-workforce-reports') else m.isfile(),'MOUNT_ROOT_TYPE_INVALID')
        if m.isfile():
            f=a.extractfile(m);read=0
            while True:
                b=f.read(131072)
                if not b:break
                read+=len(b)
            need(read==m.size,'MOUNT_TRUNCATED')
        count+=1
    need(count>0,'MOUNT_EMPTY_ARCHIVE')

def images(stream,expected):
    records={};manifest=None
    for name,m,a in entries(stream,50000):
        if m.isdir():continue
        h=hashlib.sha256();f=a.extractfile(m);read=0;small=bytearray() if name=='manifest.json' else None
        while True:
            b=f.read(131072)
            if not b:break
            read+=len(b);h.update(b)
            if small is not None:
                need(read<=MAX_SMALL,'IMAGE_MANIFEST_TOO_LARGE');small.extend(b)
        need(read==m.size,'IMAGE_ARCHIVE_TRUNCATED');records[name]=(h.hexdigest(),read)
        if small is not None:manifest=json_object(bytes(small))
    need(isinstance(manifest,list) and len(manifest)==4,'FOUR_DOCKER_MANIFESTS_REQUIRED')
    configs=set()
    for row in manifest:
        config=safe_name(row['Config']);need(config in records,'IMAGE_CONFIG_MISSING')
        configs.add('sha256:'+records[config][0])
        layers=row.get('Layers');need(isinstance(layers,list) and layers,'IMAGE_LAYERS_MISSING')
        for layer in layers:
            path=safe_name(layer);need(path in records and records[path][1]>0,'IMAGE_LAYER_REFERENCE_MISSING')
    need(configs==expected and len(configs)==4,'IMAGE_CONFIG_ID_MISMATCH')
    # Layer presence is checked. This does not attest OCI graph/diff-ID identity.

def verify_receipt(root):
    receipt=root/'SHA256SUMS';need(receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size<8192,'HASH_RECEIPT_UNSAFE')
    hashes={}
    for line in receipt.read_text().splitlines():
        match=re.fullmatch(r'([a-f0-9]{64})  ([a-z0-9.-]+\.gpg)',line)
        need(match is not None and match[2] not in hashes,'HASH_RECEIPT_INVALID');hashes[match[2]]=match[1]
    need(len(hashes)==12,'TWELVE_ARCHIVES_REQUIRED')
    for name,digest in hashes.items():
        path=root/name
        need(path.is_file() and not path.is_symlink() and path.stat().st_uid==os.getuid() and not path.stat().st_mode&0o077,'CIPHERTEXT_FILE_UNSAFE')
        h=hashlib.sha256()
        with path.open('rb') as f:
            for b in iter(lambda:f.read(131072),b''):h.update(b)
        need(h.hexdigest()==digest,'CIPHERTEXT_HASH_CHANGED')
    return set(hashes)
def audit(root):
    need(socket.gethostname()=='firelion-Aspire-A315-51' and os.getuid()!=0,'ACER_NONROOT_ONLY')
    need(root==ROOT and root.is_dir() and not root.is_symlink() and root.stat().st_uid==os.getuid() and not root.stat().st_mode&0o077,'BACKUP_ROOT_UNSAFE')
    swaps=subprocess.run(['swapon','--show=NAME','--noheadings','--raw'],capture_output=True,check=True,timeout=10)
    need(not swaps.stdout.strip(),'ACTIVE_SWAP_REFUSED')
    available={x.split(':')[0]:int(x.split()[1]) for x in Path('/proc/meminfo').read_text().splitlines()}
    need(available.get('MemAvailable',0)>=4*1024**2,'AVAILABLE_RAM_BELOW_4_GIB')
    names=verify_receipt(root)
    with decrypted(root/'runtime-and-config.tar.gpg') as f:rows=configuration(f)
    mounts=mapping(rows)
    need(names==set(mounts)|{'runtime-and-config.tar.gpg','original-app-images.tar.gpg',*(n+'.dump.gpg' for n in DBS)},'ARCHIVE_SET_MAPPING_MISMATCH')
    print('CURRENT_P1_RUNTIME_AND_MOUNT_MAPPING=PASS',flush=True)
    for name,destination in mounts.items():
        with decrypted(root/name) as f:mount_archive(f,destination)
    print('CURRENT_P1_MOUNT_ARCHIVE_STRUCTURE=PASS_8_OF_8',flush=True)
    for name in DBS:
        with decrypted(root/(name+'.dump.gpg')) as f:need(f.read(5)==b'PGDMP','POSTGRES_CUSTOM_HEADER_INVALID')
    print('CURRENT_P1_DATABASE_CUSTOM_HEADERS=PASS_2_OF_2',flush=True)
    with decrypted(root/'original-app-images.tar.gpg') as f:images(f,{r['Image'] for r in rows.values()})
    print('CURRENT_P1_ARCHIVED_IMAGE_CONFIG_IDS=PASS_4_OF_4',flush=True)
    print('CURRENT_P1_ARCHIVE_FORMAT_AUDIT=PASS',flush=True)
    print('OCI_GRAPH_AND_LAYER_DIFF_IDS=NOT_VERIFIED')
    print('RESTORE=NOT_PERFORMED')
    print('R1_CUSTOMER_RELEASE=NO_GO')
if __name__=='__main__':
    try:
        parser=argparse.ArgumentParser();parser.parse_args();audit(ROOT)
    except BaseException as e:
        print('STOP='+ (str(e) if isinstance(e,Stop) else 'ARCHIVE_AUDIT_FAILED_REDACTED'),flush=True)
        print('R1_CUSTOMER_RELEASE=NO_GO');sys.exit(1)
