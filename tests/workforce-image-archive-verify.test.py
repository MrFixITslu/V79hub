import hashlib,importlib.util,io,json,tarfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('verifier',Path(__file__).parents[1]/'scripts/workforce-image-archive-verify.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)

def fixture(missing=False,tamper=False,wrong_config=False):
 blobs={}
 def add(obj):
  raw=json.dumps(obj).encode() if isinstance(obj,dict) else obj
  digest='sha256:'+hashlib.sha256(raw).hexdigest();blobs[digest]=raw
  return {'digest':digest,'size':len(raw)}
 config=add({'rootfs':{'type':'layers','diff_ids':[]},'config':{'Env':['PRIVATE_VALUE']}})
 layer=add(b'synthetic layer')
 manifest=add({'config':config,'layers':[layer]})
 root=add({'manifests':[manifest]})
 if missing:del blobs[layer['digest']]
 if tamper:blobs[layer['digest']]=b'corrupt layer'
 out=io.BytesIO()
 with tarfile.open(fileobj=out,mode='w') as t:
  entries={'blobs/sha256/'+k.removeprefix('sha256:'):val for k,val in blobs.items()}
  entries['index.json']=json.dumps({'manifests':[root]}).encode()
  entries['manifest.json']=json.dumps([{'Config':'blobs/sha256/'+('0'*64 if wrong_config else config['digest'].removeprefix('sha256:'))}]).encode()
  for name,raw in entries.items():
   member=tarfile.TarInfo(name);member.size=len(raw);t.addfile(member,io.BytesIO(raw))
 out.seek(0);return out,root['digest']

class GraphTests(unittest.TestCase):
 def test_nested_index_to_manifest_to_config_and_layer(self):
  source,root=fixture();result=v.verify(source,root)
  self.assertEqual(result['reachableBlobs'],4);self.assertNotIn('PRIVATE_VALUE',str(result))
 def test_missing_layer(self):
  source,root=fixture(missing=True)
  with self.assertRaises(ValueError):v.verify(source,root)
 def test_corrupt_blob(self):
  source,root=fixture(tamper=True)
  with self.assertRaises(ValueError):v.verify(source,root)
 def test_wrong_docker_manifest_link(self):
  source,root=fixture(wrong_config=True)
  with self.assertRaises(ValueError):v.verify(source,root)
 def test_wrong_live_identity(self):
  source,root=fixture()
  with self.assertRaises(ValueError):v.verify(source,'sha256:'+'0'*64)

if __name__=='__main__':unittest.main()
