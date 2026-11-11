import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_review', ROOT / 'scripts/review-hardened-release.py')
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


class ReviewTests(unittest.TestCase):
    def fixture(self):
        contract = {'__name__': 'test_contract'}
        exec(reviewer.CONTRACT_SOURCE, contract)
        pins = {**contract['CURRENT'], 'v79-business-agent': 'fixed-agent',
                'v79-hub-postgres': 'fixed-hub-db', 'tiquet-postgres': 'fixed-tiquet-db'}
        rows, models, old_images, configs, files = {}, {}, {}, {}, {}
        for name, image in pins.items():
            rows[name] = {'Name': '/' + name, 'Id': name + '-original-id', 'Image': image,
                          'State': {'Running': True, 'Health': {'Status': 'healthy'}},
                          'Config': {'Labels': {}, 'Env': []}, 'HostConfig': {}, 'Mounts': [],
                          'NetworkSettings': {'Networks': {'existing': {}}}}
            if name not in reviewer.EXPECTED:
                continue
            user = 'appuser' if name == 'v79-tiquet-manager' else ''
            config = {'Env': ['PATH=/bin'], 'User': user, 'WorkingDir': '/app',
                      'Entrypoint': ['entrypoint'], 'Cmd': ['node','server'],
                      'ExposedPorts': {'3000/tcp': {}}}
            old_images['old-ref-' + name] = {'Id': image, 'Config': copy.deepcopy(config)}
            old_images['old-ref-' + name]['Config']['Env'] += ['NODE_VERSION=old-runtime-version','YARN_VERSION=old-tool-version']
            config['Labels'] = {'org.opencontainers.image.revision': reviewer.EXPECTED[name][1]}
            configs[name] = {'Id': 'sha256:' + reviewer.EXPECTED[name][0], 'Config': config}
            env = {'WIPAY_ENV': 'sandbox', 'SECRET': 'synthetic-secret-do-not-return',
                   **{'PLAN_PRICE_' + tier: '$' + str(100+i) for i,tier in enumerate(('STARTER','PRO','ENTERPRISE'))}}
            models[name] = {'name':name, 'services': {
                name: {'image':'old-ref-' + name,'environment':env,'read_only':True,
                       'volumes':[{'type':'bind','source':'/existing','target':'/app/data'}]},
                'database': {'image':'unchanged','volumes':['original:/data']}},
                'networks':{'existing':{'external':True}}}
            rows[name]['Config']['Env'] = [k+'='+v for k,v in env.items()]
            rows[name]['Config']['Labels'] = {
                'com.docker.compose.project.working_dir': '/home/firelion/project',
                'com.docker.compose.project': name,
                'com.docker.compose.service': name}
            files[name] = [{'path':f'/home/firelion/file{i}.json','sha256':sha,'bytes':20}
                           for i,sha in enumerate(reviewer.INPUT_HASHES[name])]
        fingerprints = {name: self.digest({'Config': row['Config'], 'HostConfig': row['HostConfig'],
                        'Mounts':row['Mounts'],'Networks':['existing']})
                        for name,row in rows.items() if name in reviewer.EXPECTED}
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            if args[:2] == ['docker','inspect']:
                return copy.deepcopy(list(rows.values()))
            if args[:3] == ['docker','image','inspect']:
                return copy.deepcopy([old_images[args[3]]])
            if args[:2] == ['docker','compose']:
                return copy.deepcopy(models[args[args.index('--project-name')+1]])
            raise AssertionError('Unexpected command')

        ns = {'PINS':pins,'run':run,'digest':self.digest,
              'input_files':lambda row:copy.deepcopy(files[row['Name'].lstrip('/')]),
              'interpolation_context':lambda row,files:({}, []),
              'envmap':lambda env:dict(v.split('=',1) for v in env),
              'health':lambda value:value or {}}
        overlays = []

        def render(args,directory,extra,overlay):
            name = args[args.index('--project-name')+1]
            overlays.append((copy.deepcopy(overlay), copy.deepcopy(extra)))
            model = copy.deepcopy(models[name])
            model['services'][name]['image'] = overlay['services'][name]['image']
            return model

        return {'payload':{'configs':configs}, 'ns':ns, 'render':render,
                'fingerprints':fingerprints,'rows':rows,'models':models,'files':files,
                'calls':calls,'overlays':overlays,'old_images':old_images}

    @staticmethod
    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def execute(self, f, render=None):
        with patch.dict(reviewer.RUNTIME_FINGERPRINTS,f['fingerprints'],clear=True):
            return reviewer.review(f['payload'],f['ns'],render or f['render'])

    def test_embedded_contract_is_exact_source(self):
        self.assertEqual(reviewer.CONTRACT_SOURCE,(ROOT/'scripts/paired-image-release-contract.py').read_text())

    def test_both_current_models_candidate_and_rollback_without_mutation(self):
        f=self.fixture();before=copy.deepcopy(f['rows']);result=self.execute(f)
        self.assertEqual(len(result['apps']),2)
        self.assertFalse(result['production_mutations']);self.assertFalse(result['images_loaded'])
        self.assertEqual(result['release_decision'],'HOLD')
        self.assertEqual(f['rows'],before)
        self.assertNotIn('synthetic-secret',json.dumps(result))
        for row in result['apps'].values():
            self.assertTrue(row['rollback_complete_model_match'])
            self.assertEqual(row['image_defaults']['reviewed_removed_base_metadata_names'],['NODE_VERSION','YARN_VERSION'])
        self.assertEqual(len(f['overlays']),4)
        self.assertTrue(all(args[1] in ('inspect','image','compose') for args in f['calls']))

    def test_frozen_prices_are_only_subprocess_context(self):
        f=self.fixture();self.execute(f)
        tiquet=[extra for overlay,extra in f['overlays'] if 'v79-tiquet-manager' in overlay['services']]
        self.assertEqual(tiquet[0]['V79_P1_FROZEN_PLAN_PRICE_STARTER'],'$100')
        self.assertNotIn('V79_P1_FROZEN_PLAN_PRICE_STARTER',f['models']['v79-tiquet-manager']['services']['v79-tiquet-manager']['environment'])

    def test_new_runtime_flag_or_price_change_rejected(self):
        for key,value in [('V79_REQUIRE_ADMIN_MFA','0'),('PLAN_PRICE_STARTER','$999')]:
            f=self.fixture()
            def render(*args):
                model=f['render'](*args)
                service=next(iter(args[3]['services']))
                model['services'][service]['environment'][key]=value
                return model
            with self.subTest(key=key), self.assertRaises(reviewer.Refused):self.execute(f,render)

    def test_other_service_and_mount_changes_rejected(self):
        for target in ('mount','database'):
            f=self.fixture()
            def render(*args):
                model=f['render'](*args);service=next(iter(args[3]['services']))
                if target=='mount':model['services'][service]['volumes']=[]
                else:model['services']['database']['image']='changed'
                return model
            with self.subTest(target=target),self.assertRaises(reviewer.Refused):self.execute(f,render)

    def test_rollback_must_be_complete_original_model(self):
        f=self.fixture()
        def render(*args):
            model=f['render'](*args);service=next(iter(args[3]['services']))
            if args[3]['services'][service]['image']==f['ns']['PINS'][service]:
                model['services'][service]['read_only']=False
            return model
        with self.assertRaises(reviewer.Refused):self.execute(f,render)

    def test_unknown_default_environment_change_rejected(self):
        f=self.fixture();f['payload']['configs']['v79-hub']['Config']['Env'].append('UNAPPROVED_AUTH_FLAG=1')
        with self.assertRaisesRegex(reviewer.Refused,'INHERITED_IMAGE_ENVIRONMENT_CHANGED'):self.execute(f)

    def test_tool_metadata_changes_cannot_hide_new_values(self):
        f=self.fixture();f['payload']['configs']['v79-hub']['Config']['Env'].append('NODE_VERSION=unexpected-new-metadata')
        with self.assertRaises(reviewer.Refused):self.execute(f)

    def test_original_image_reference_resolution_required(self):
        f=self.fixture();f['old_images']['old-ref-v79-hub']['Id']='wrong'
        with self.assertRaises(reviewer.Refused):self.execute(f)

    def test_all_five_core_images_and_health_guarded(self):
        for field in ('Image','State'):
            f=self.fixture();row=f['rows']['v79-business-agent']
            row[field]='changed' if field=='Image' else {'Running':False,'Health':{'Status':'unhealthy'}}
            with self.subTest(field=field),self.assertRaises(reviewer.Refused):self.execute(f)

    def test_accepted_compose_order_and_hashes_required(self):
        f=self.fixture();f['files']['v79-hub'].reverse()
        with self.assertRaises(reviewer.Refused):self.execute(f)

    def test_container_replacement_during_read_rejected(self):
        f=self.fixture();original=f['ns']['run'];count=0
        def run(args,**kwargs):
            nonlocal count
            data=original(args,**kwargs)
            if args[:2]==['docker','inspect']:
                count+=1
                if count==2:data[0]['Id']='replaced'
            return data
        f['ns']['run']=run
        with self.assertRaises(reviewer.Refused):self.execute(f)

    def test_runtime_change_and_input_file_change_during_read_rejected(self):
        for target in ('runtime','file'):
            f=self.fixture();original=f['render'];count=0
            def render(*args):
                nonlocal count
                data=original(*args);count+=1
                if count==4:
                    if target=='runtime':f['rows']['v79-hub']['HostConfig']['Privileged']=True
                    else:f['files']['v79-hub'][0]['sha256']='changed'
                return data
            with self.subTest(target=target),self.assertRaises(reviewer.Refused):self.execute(f,render)


if __name__=='__main__':unittest.main()
