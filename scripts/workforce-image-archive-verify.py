#!/usr/bin/env python3
"""Stream-verify Docker/OCI archive digests and reachable graph; never load images."""
import hashlib,json,re,subprocess,sys,tarfile

EXPECTED='sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06'

def verify(source, expected=EXPECTED):
 if not re.fullmatch('sha256:[0-9a-f]{64}',expected):raise ValueError('Invalid expected image identity')
 blobs={};nodes={};index=None;docker_manifest=None
 with tarfile.open(fileobj=source,mode='r|') as archive:
  for member in archive:
   name=member.name.removeprefix('./')
   if not member.isfile():continue
   digest_name=None
   if re.fullmatch(r'blobs/sha256/[0-9a-f]{64}',name):digest_name='sha256:'+name.rsplit('/',1)[1]
   if digest_name:
    if digest_name in blobs:raise ValueError('Duplicate blob')
    h=hashlib.sha256();count=0;small=bytearray() if member.size<=2_000_000 else None
    data=archive.extractfile(member)
    while chunk:=data.read(1024*1024):
     h.update(chunk);count+=len(chunk)
     if small is not None:small.extend(chunk)
    if count!=member.size or 'sha256:'+h.hexdigest()!=digest_name:raise ValueError('Blob digest/size mismatch')
    blobs[digest_name]=count
    if small is not None:
     try:obj=json.loads(small)
     except (ValueError,UnicodeDecodeError):continue
     # Keep only graph structure, never image environment, labels or history.
     if isinstance(obj,dict):
      if isinstance(obj.get('manifests'),list):nodes[digest_name]=('index',obj['manifests'])
      elif isinstance(obj.get('config'),dict) and isinstance(obj.get('layers'),list):nodes[digest_name]=('manifest',[obj['config'],*obj['layers']])
      elif isinstance(obj.get('rootfs'),dict):nodes[digest_name]=('config',[])
   elif name in ['index.json','manifest.json']:
    if member.size>2_000_000:raise ValueError('Oversized archive index')
    obj=json.load(archive.extractfile(member))
    if name=='index.json':
     if index is not None:raise ValueError('Duplicate index')
     index=obj
    else:
     if docker_manifest is not None:raise ValueError('Duplicate Docker manifest')
     docker_manifest=obj
 if not blobs or not isinstance(index,dict) or not isinstance(index.get('manifests'),list):raise ValueError('OCI archive index unavailable')
 roots=[d for d in index['manifests'] if isinstance(d,dict) and d.get('digest')==expected]
 if len(roots)!=1:raise ValueError('Expected live image absent from archive index')
 seen=set();configs=set();manifests=0
 def walk(descriptor,ancestors):
  nonlocal manifests
  if not isinstance(descriptor,dict):raise ValueError('Invalid graph descriptor')
  digest=descriptor.get('digest');size=descriptor.get('size')
  if digest not in blobs or not isinstance(size,int) or isinstance(size,bool) or size!=blobs[digest]:raise ValueError('Missing or incorrectly sized graph blob')
  if digest in ancestors:raise ValueError('Cyclic graph')
  if digest in seen:return
  seen.add(digest)
  kind,children=nodes.get(digest,('layer',[]))
  if kind=='config':configs.add(digest)
  elif kind=='manifest':manifests+=1
  for child in children:walk(child,ancestors|{digest})
 walk(roots[0],set())
 if not manifests or not configs:raise ValueError('No reachable image manifest/config')
 if not isinstance(docker_manifest,list) or not any(isinstance(row,dict) and 'sha256:'+str(row.get('Config','')).removeprefix('./').removeprefix('blobs/sha256/') in configs for row in docker_manifest):raise ValueError('Docker manifest does not reference a reachable config')
 return {'hashedBlobs':len(blobs),'reachableBlobs':len(seen),'reachableImageManifests':manifests,'reachableConfigs':len(configs),'rootImage':expected}

def main():
 if len(sys.argv)!=2:raise ValueError('Provide the encrypted original-image archive')
 decrypt=subprocess.Popen(['gpg','--quiet','--decrypt',sys.argv[1]],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
 try:
  result=verify(decrypt.stdout)
  # Consume any remaining encrypted plaintext so GPG integrity validation completes.
  while decrypt.stdout.read(1024*1024):pass
  if decrypt.wait():raise ValueError('Decryption integrity failed')
 finally:
  if decrypt.poll() is None:decrypt.kill();decrypt.wait()
 print('ORIGINAL_IMAGE_OCI_GRAPH=PASS')
 print('ROOT_IMAGE='+result['rootImage'])
 print('HASHED_BLOBS='+str(result['hashedBlobs']))
 print('REACHABLE_BLOBS='+str(result['reachableBlobs']))
 print('DOCKER_MANIFEST_LINK=PASS')
 print('IMAGE_LOADED=NO')

if __name__=='__main__':
 try:main()
 except Exception:
  print('ORIGINAL_IMAGE_OCI_GRAPH=FAILED');raise SystemExit(1)
