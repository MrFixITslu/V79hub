"""Fresh receipt binding checks; no server or Docker calls."""
import copy
import datetime
import importlib.util
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'scripts/marketing-production-reconcile-fresh-generation.py'

class FreshReceiptTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('fresh_reconciliation',SOURCE)
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        m=self.m
        original_paths=m.HUB_FILES+m.MARKETING_FILES+['/opt/v79/hub/.env','/home/firelion/V79Marketing/.env']
        self.history={'configurationHashes':{path:'a'*64 for path in original_paths},
                      'preparedOverlayHashes':{name:'b'*64 for name in m.PREPARED}}
        source_paths={str(m.RECOVERY/'rehearsal-receipt.json'),str(m.WORK/'manifest.json'),str(m.WORK/'deployment-disabled.json'),
            str(m.ACTIVATION/'manifest.json'),str(m.ACTIVATION/'failure.json'),str(m.ACTIVATION/'switch-attempted-v79-hub.json')}
        source_paths.update(str(m.RECOVERY/name) for name in m.PREPARED)
        source_paths.update(str(m.ACTIVATION/('enable-'+name+'.yml')) for name in m.SPECS)
        sources={path:'c'*64 for path in source_paths}
        runtime=dict(m.BASELINES);runtime.update({'v79-hub':m.CANDIDATE,'v79marketing-app':m.MARKETING_CANDIDATE})
        self.receipt={'mode':'fresh-checkpoint-for-reviewed-partial-activation',
            'candidateImage':m.CANDIDATE,'candidateCommit':m.SHA,'marketingCandidateImage':m.MARKETING_CANDIDATE,'marketingCandidateCommit':m.MARKETING_SHA,
            'runtimeImages':runtime,'rollbackImages':m.BASELINES,'existingG3KeysReused':True,'liveDeploymentPerformed':False,
            'liveGenerationFlags':{'v79-hub':'1','v79marketing-app':'0'},'livePublicationEnabled':False,
            'sourceRecoveryDirectory':str(m.RECOVERY),'sourceCutoverDirectory':str(m.WORK),'sourceActivationDirectory':str(m.ACTIVATION),
            'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'encryptedBackups':{name:'d'*64 for name in m.BACKUPS},'preparedOverlayHashes':self.history['preparedOverlayHashes'],
            'liveRuntimeIds':{name:'container-'+name for name in m.BASELINES},'sourceDocumentHashes':sources,
            'configurationHashes':dict(self.history['configurationHashes'],**sources)}
        for field in ('snapshotRestoreVerified','isolatedStartupRollbackVerified','copiedIdentityBillingPreserved',
            'scratchCleanupVerified','liveContainerIdsUnchanged','marketingOnlineBackupRestored','marketingOriginalAndCandidateStartupVerified',
            'marketingRollbackWithCopiedG3SchemaVerified','pairedG3SignatureReplayAndPublishDisabledVerified','copiedG2AcceptedWorkItemPreserved'):
            self.receipt[field]=True

    def test_fresh_scope_and_original_key_binding_pass(self):
        self.m.verify_fresh_receipt(self.receipt,self.history)

    def test_only_unset_image_user_accepts_runtime_empty_string(self):
        m=self.m
        image={'User':None,'Cmd':['node','server'],'Entrypoint':['docker-entrypoint.sh'],'WorkingDir':'/app'}
        runtime=dict(image,User='')
        m.verify_application_profile({},image,runtime)
        for value in ('root','0','0:0','node','1000',False,[]):
            with self.assertRaises(RuntimeError):m.verify_application_profile({},image,dict(runtime,User=value))
        configured=dict(image,User='node')
        m.verify_application_profile({},configured,dict(runtime,User='node'))
        with self.assertRaises(RuntimeError):m.verify_application_profile({},configured,runtime)
        with self.assertRaises(RuntimeError):m.verify_application_profile({'user':'node'},image,runtime)

    def test_command_entrypoint_workdir_and_explicit_user_stay_exact(self):
        m=self.m
        image={'User':'node','Cmd':['node','server'],'Entrypoint':['docker-entrypoint.sh'],'WorkingDir':'/app'}
        m.verify_application_profile({},image,image)
        for field,value in [('User','root'),('Cmd',['sh']),('Entrypoint',[]),('WorkingDir','/tmp')]:
            with self.assertRaises(RuntimeError):m.verify_application_profile({},image,dict(image,**{field:value}))
        m.verify_application_profile({'user':'1000:1000'},image,dict(image,User='1000:1000'))
        with self.assertRaises(RuntimeError):m.verify_application_profile({'user':'1000:1000'},image,image)

    def test_stale_and_future_fresh_dates_stop(self):
        for delta in (datetime.timedelta(hours=-2),datetime.timedelta(hours=2)):
            bad=copy.deepcopy(self.receipt);bad['capturedAt']=(datetime.datetime.now(datetime.timezone.utc)+delta).isoformat()
            with self.assertRaises(RuntimeError):self.m.verify_fresh_receipt(bad,self.history)

    def test_changed_publication_keys_flags_candidates_or_restore_evidence_stop(self):
        for field,value in [('livePublicationEnabled',True),('existingG3KeysReused',False),('candidateImage','other'),
            ('liveGenerationFlags',{'v79-hub':'1','v79marketing-app':'1'}),('pairedG3SignatureReplayAndPublishDisabledVerified',False)]:
            bad=copy.deepcopy(self.receipt);bad[field]=value
            with self.assertRaises(RuntimeError):self.m.verify_fresh_receipt(bad,self.history)
        bad=copy.deepcopy(self.receipt);bad['preparedOverlayHashes']['g3-protected-keys.json']='rotated'
        with self.assertRaises(RuntimeError):self.m.verify_fresh_receipt(bad,self.history)

    def test_missing_or_extra_backup_runtime_or_source_evidence_stops(self):
        for field in ('encryptedBackups','liveRuntimeIds','sourceDocumentHashes','configurationHashes'):
            bad=copy.deepcopy(self.receipt);bad[field].pop(next(iter(bad[field])))
            with self.assertRaises(RuntimeError):self.m.verify_fresh_receipt(bad,self.history)
            bad=copy.deepcopy(self.receipt);bad[field]['unexpected']='unapproved'
            with self.assertRaises(RuntimeError):self.m.verify_fresh_receipt(bad,self.history)

    def test_fresh_config_hashes_cannot_replace_original_provenance(self):
        bad=copy.deepcopy(self.receipt);bad['configurationHashes'][self.m.HUB_FILES[0]]='changed'
        with self.assertRaises(RuntimeError):self.m.verify_fresh_receipt(bad,self.history)
        bad=copy.deepcopy(self.receipt);path=str(self.m.ACTIVATION/'manifest.json');bad['sourceDocumentHashes'][path]='changed'
        with self.assertRaises(RuntimeError):self.m.verify_fresh_receipt(bad,self.history)

if __name__=='__main__':unittest.main()
