import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('mount_contract',Path(__file__).resolve().parents[1]/'scripts/paired-mount-contract.py')
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)


class MountTests(unittest.TestCase):
    def rows(self):
        before={'HostConfig':{'Binds':['/existing:/app/data:ro,rprivate','original:/volume:rw,nocopy'],
                 'Mounts':None,'ReadonlyRootfs':True,'CapDrop':['ALL'],'Memory':1073741824,
                 'LogConfig':{'Type':'json-file','Config':{}}},
                'Mounts':[{'Type':'bind','Source':'/existing','Destination':'/app/data','RW':False,'Mode':'ro,rprivate','Propagation':'rprivate'},
                          {'Type':'volume','Name':'original','Source':'/var/lib/docker/volumes/original/_data','Driver':'local','Destination':'/volume','RW':True,'Mode':'rw,nocopy','Propagation':''}]}
        after=copy.deepcopy(before);after['HostConfig']['Binds']=None
        after['HostConfig']['Mounts']=[{'Type':'bind','Source':'/existing','Target':'/app/data','ReadOnly':True,'BindOptions':{'CreateMountpoint':True}},
                                     {'Type':'volume','Source':'original','Target':'/volume','VolumeOptions':{'NoCopy':True}}]
        after['Mounts'][0]['Mode']='ro';after['Mounts'][1]['Mode']=''
        return before,after

    def test_equivalent_encodings_preserve_every_other_host_field(self):
        before,after=self.rows();snapshot=copy.deepcopy(before)
        self.assertTrue(contract.verify_host_storage(before,after)['host_and_storage_semantics_match'])
        self.assertEqual(before,snapshot)

    def test_no_copy_and_subpath_are_not_ignored(self):
        for key,value in [('NoCopy',False),('Subpath','other'),('Labels',{'purpose':'changed'}),('DriverConfig',{'Name':'local','Options':{'type':'nfs'}})]:
            before,after=self.rows();after['HostConfig']['Mounts'][1]['VolumeOptions'][key]=value
            with self.subTest(key=key),self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)

    def test_bind_creation_propagation_and_recursion_are_preserved(self):
        for key,value in [('CreateMountpoint',False),('Propagation','rshared'),('NonRecursive',True),('ReadOnlyNonRecursive',True),('ReadOnlyForceRecursive',True)]:
            before,after=self.rows();after['HostConfig']['Mounts'][0]['BindOptions'][key]=value
            with self.subTest(key=key),self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)

    def test_read_only_source_and_actual_mount_identity_are_preserved(self):
        for target in ('read_only','source','driver','resolved_source'):
            before,after=self.rows()
            if target=='read_only':after['Mounts'][0]['RW']=True
            elif target=='source':after['HostConfig']['Mounts'][0]['Source']='/different'
            elif target=='driver':after['Mounts'][1]['Driver']='different'
            else:after['Mounts'][1]['Source']='/different'
            with self.subTest(target=target),self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)

    def test_all_other_host_fields_remain_strict(self):
        for key,value in [('Privileged',True),('ReadonlyRootfs',False),('CapAdd',['SYS_ADMIN']),('Memory',0),('LogConfig',{'Type':'none'}),('NetworkMode','host'),('Tmpfs',{'/secret':'rw'})]:
            before,after=self.rows();after['HostConfig'][key]=value
            with self.subTest(key=key),self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)

    def test_unknown_options_and_mount_types_reject(self):
        for target in ('top','bind','volume','runtime','type'):
            before,after=self.rows()
            if target=='top':after['HostConfig']['Mounts'][0]['FutureOption']=True
            elif target=='bind':after['HostConfig']['Mounts'][0]['BindOptions']['Unknown']=True
            elif target=='volume':after['HostConfig']['Mounts'][1]['VolumeOptions']['Unknown']=True
            elif target=='runtime':after['Mounts'][0]['Unknown']=True
            else:after['HostConfig']['Mounts'][0]['Type']='image'
            with self.subTest(target=target),self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)

    def test_duplicate_missing_and_unaccounted_mounts_reject(self):
        for target in ('duplicate_decl','duplicate_actual','missing_decl','missing_actual'):
            before,after=self.rows()
            if target=='duplicate_decl':after['HostConfig']['Mounts'].append(copy.deepcopy(after['HostConfig']['Mounts'][0]))
            elif target=='duplicate_actual':after['Mounts'].append(copy.deepcopy(after['Mounts'][0]))
            elif target=='missing_decl':after['HostConfig']['Mounts'].pop()
            else:after['Mounts'].pop()
            with self.subTest(target=target),self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)

    def test_selinux_labels_are_not_silently_dropped(self):
        before,after=self.rows();before['HostConfig']['Binds'][0]+=',z';before['Mounts'][0]['Mode']+=',z'
        with self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)

    def test_ambiguous_paths_and_conflicting_modes_reject(self):
        for bind in ('/existing:/app/data:ro,rw','/existing:/app/data:rprivate,rshared','/existing/../else:/app/data:ro','/existing:/app/data:unknown','/app/data'):
            before,after=self.rows();before['HostConfig']['Binds'][0]=bind
            with self.subTest(bind=bind),self.assertRaises(contract.Refused):contract.verify_host_storage(before,after)


if __name__=='__main__':unittest.main()
