import ast
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'scripts/p1-offhost-metadata-readonly.py'
spec=importlib.util.spec_from_file_location('metadata',PATH)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
CURRENT={k:'sha256:'+'a'*64 for k in m.NAMES}
def manifest():
    names=m.REQUIRED|{k+'-mount-0.tar.gpg' for k in m.NAMES}
    return {'source_images':CURRENT.copy(),'files':[{'name':n,'sha256':'b'*64,'bytes':100} for n in sorted(names)]}

class MetadataTests(unittest.TestCase):
    def test_candidate_images_are_not_snapshot_source_images(self):
        data=manifest();data['source_images']={};data['candidates']=CURRENT.copy()
        self.assertFalse(m.classify(data,CURRENT))

    def test_missing_scope_bad_paths_duplicate_and_bad_size_rejected(self):
        for field,value in [('name','../private.gpg'),('sha256','invalid'),('bytes',0),('bytes',True)]:
            data=manifest();data['files'][0][field]=value
            self.assertFalse(m.classify(data,CURRENT))
        data=manifest();data['files'].append(data['files'][0])
        self.assertFalse(m.classify(data,CURRENT))
        data=manifest();data['source_images']['v79-hub']='sha256:'+'c'*64
        self.assertFalse(m.classify(data,CURRENT))

    def test_metadata_match_checks_files_and_sizes_without_hashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'v79-portfolio-rollout.ABC12345-local';run.mkdir();cp=run/'checkpoint';cp.mkdir()
            data=manifest();p=cp/'manifest.json';p.write_text(json.dumps(data));p.chmod(0o600)
            for item in data['files']:(cp/item['name']).write_bytes(b'x'*100)
            # Deliberately false hashes: this inventory must NOT claim hash verification.
            self.assertTrue(m.inventory(CURRENT,root))
            (cp/data['files'][0]['name']).write_bytes(b'x')
            with self.assertRaisesRegex(m.Stop,'SIZE_CHANGED'):m.inventory(CURRENT,root)

    def test_symlinked_run_rejected_and_empty_scope_reports_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.assertFalse(m.inventory(CURRENT,root))
            (root/'v79-portfolio-rollout.ABC12345-local').symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(m.Stop,'RUN_UNSAFE'):m.inventory(CURRENT,root)

    def test_scope_has_no_backup_decryption_database_or_mutation(self):
        for source in (PATH.read_text(),m.SERVER):
            tree=ast.parse(source)
            constants=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
            self.assertFalse(set(constants)&{'pg_dump','pg_restore','psql','--decrypt','--encrypt','rm','prune','create','start','stop','restart','import','load','systemctl'})
        self.assertIn("'container','inspect'",m.SERVER)

if __name__=='__main__':unittest.main()
