import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('audit',ROOT/'scripts/p1-current-offhost-archive-audit.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
def tar(items):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w') as t:
        for name,raw,kind in items:
            m=tarfile.TarInfo(name);m.mode=0o600
            if kind=='dir':m.type=tarfile.DIRTYPE
            elif kind=='link':m.type=tarfile.SYMTYPE;m.linkname='PRIVATE_MARKER'
            elif kind=='privileged':m.mode=0o4755
            else:m.size=len(raw)
            t.addfile(m,io.BytesIO(raw) if m.isfile() else None)
    output.seek(0);return output
class AuditTests(unittest.TestCase):
    def rows(self):
        rows={n:{'Name':'/'+n,'Id':str(i)*64,'Image':'sha256:'+str(i)*64} for i,n in enumerate(a.APPS+a.DBS,1)}
        rows[a.DBS[0]]['Image']='sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24'
        rows[a.DBS[1]]['Image']='sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685'
        mounts=['/app/data','/app/logs','/run/secrets/v79-agent-token','/run/secrets/v79-workforce-token','/run/secrets/v79-readonly-platform-token','/run/secrets/v79-coo-github-token']
        rows[a.APPS[0]]['Mounts']=[{'Destination':x,'Type':'bind'} for x in mounts]
        rows[a.APPS[1]]['Mounts']=[{'Destination':x,'Type':'volume'} for x in ['/app/data','/app/uploads']]
        return rows
    def config(self,rows=None):
        files={'runtime.json':json.dumps(rows or self.rows()).encode(),'frozen-compose.json':json.dumps({n:{} for n in a.APPS}).encode(),'input-map.json':b'{"0":"/opt/compose.yml"}','config/0':b'PRIVATE_MARKER'}
        return tar([(n,v,'file') for n,v in files.items()])
    def test_actual_capture_schema_only_two_frozen_models(self):
        rows=a.configuration(self.config());self.assertEqual(len(a.mapping(rows)),8)
    def test_bad_runtime_images_names_and_ids(self):
        for field,value in [('Name','/unexpected'),('Id','bad'),('Image','bad')]:
            rows=self.rows();rows[a.APPS[0]][field]=value
            with self.assertRaises(a.Stop):a.configuration(self.config(rows))
        rows=self.rows();rows[a.DBS[0]]['Image']='sha256:'+'a'*64
        with self.assertRaisesRegex(a.Stop,'DATABASE_IMAGE_CHANGED'):a.configuration(self.config(rows))
    def test_mount_mapping_wrong_duplicate_and_persistent(self):
        for value in [{'Destination':'/etc','Type':'bind'},{'Destination':'/app/data','Type':'bind'},{'Destination':'/app/uploads','Type':'tmpfs'}]:
            rows=self.rows();rows[a.APPS[1]]['Mounts'][1]=value
            with self.assertRaises(a.Stop):a.mapping(rows)
    def test_paths_links_devices_duplicates_and_privileged_entries(self):
        for name,kind in [('../escape','file'),('/absolute','file'),('data\\escape','file'),('data/link','link'),('data/setuid','privileged')]:
            with self.assertRaises(a.Stop):list(a.entries(tar([(name,b'x',kind)])))
        with self.assertRaisesRegex(a.Stop,'DUPLICATE'):list(a.entries(tar([('data',b'','dir'),('data',b'','dir')])))
    def test_mount_roots_directory_and_token_file(self):
        a.mount_archive(tar([('data',b'','dir'),('data/test',b'PRIVATE_MARKER','file')]),'/app/data')
        a.mount_archive(tar([('v79-agent-token',b'PRIVATE_MARKER','file')]),'/run/secrets/v79-agent-token')
        with self.assertRaises(a.Stop):a.mount_archive(tar([('wrong',b'x','file')]),'/app/data')
        with self.assertRaises(a.Stop):a.mount_archive(tar([('data',b'x','file')]),'/app/data')
    def test_json_duplicate_keys_rejected(self):
        with self.assertRaisesRegex(a.Stop,'JSON_DUPLICATE_KEY'):a.json_object(b'{"x":1,"x":2}')
    def image(self,wrong=False,missing=False):
        items=[];manifest=[];expected=set()
        for i in range(4):
            raw=json.dumps({'fixture':i}).encode();digest=hashlib.sha256(raw).hexdigest();expected.add('sha256:'+digest)
            config='blobs/sha256/'+digest;layer='layer'+str(i)+'/layer.tar'
            items.append((config,raw,'file'))
            if not missing or i:items.append((layer,b'opaque layer bytes','file'))
            manifest.append({'Config':config,'Layers':[layer]})
        items.append(('manifest.json',json.dumps(manifest).encode(),'file'))
        if wrong:expected.remove(next(iter(expected)));expected.add('sha256:'+'a'*64)
        return tar(items),expected
    def test_four_config_hashes_and_all_layer_references(self):
        a.images(*self.image())
        for kwargs in [{'wrong':True},{'missing':True}]:
            with self.assertRaises(a.Stop):a.images(*self.image(**kwargs))
    def test_receipt_rejects_traversal_duplicates_and_wrong_count(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'SHA256SUMS'
            for text in ['a'*64+'  ../x.gpg\n',('a'*64+'  x.gpg\n')*12,'a'*64+'  x.gpg\n']:
                p.write_text(text)
                with self.assertRaises(a.Stop):a.verify_receipt(Path(d))
if __name__=='__main__':unittest.main()
