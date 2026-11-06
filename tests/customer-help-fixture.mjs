// Disposable full-Hub QA fixture. It never reads a production environment/store.
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomBytes,scryptSync,createHash} from 'node:crypto';
export function helpFixture() {
 const root=mkdtempSync(join(tmpdir(),'v79-customer-help-'));
 const password='Synthetic-help-customer-2026-only';
 const salt=randomBytes(16).toString('hex');
 const hash=`scrypt:${salt}:${scryptSync(password,salt,64).toString('hex')}`;
 const now=new Date().toISOString();
 const users=['viewer-a','viewer-b','revoked','suspended'].map(id=>({id,username:id,fullName:'Help QA Customer',email:id+'@example.invalid',password:hash,role:'viewer',permissions:['overview'],createdAt:now}));
 const organizations=['customer-a','customer-b','suspended-org'].map(id=>({id,name:'Example Customer Workspace',slug:id,status:id==='suspended-org'?'suspended':'active',createdAt:now}));
 const memberships=users.map(u=>({userId:u.id,organizationId:u.id==='viewer-b'?'customer-b':u.id==='suspended'?'suspended-org':'customer-a',role:'viewer',permissions:['overview'],appIds:[],status:u.id==='revoked'?'revoked':'active',createdAt:now}));
 users.push({id:'synthetic-owner',username:'admin',fullName:'Synthetic Owner',email:'vision79slu@gmail.com',password:hash,role:'admin',permissions:['overview'],createdAt:now});
 organizations.push({id:'owner-org',name:'Synthetic Owner Workspace',slug:'owner-org',status:'active',createdAt:now});
 memberships.push({userId:'synthetic-owner',organizationId:'owner-org',role:'owner',permissions:['overview'],appIds:[],status:'active',createdAt:now});
 writeFileSync(join(root,'pos-identity.json'),JSON.stringify({organizationId:'owner-org',ownerUserId:'synthetic-owner'}),{mode:0o600});
 writeFileSync(join(root,'v79_store.json'),JSON.stringify({users,workspace:{companyName:'Isolated Help QA'},organizations,memberships}),{mode:0o600});
 const tokens=Object.fromEntries(users.map(u=>[u.id,randomBytes(32).toString('hex')]));
 writeFileSync(join(root,'hub-sessions.json'),JSON.stringify({sessions:users.map(u=>({tokenHash:createHash('sha256').update(tokens[u.id]).digest('hex'),userId:u.id,username:u.username,organizationId:memberships.find(m=>m.userId===u.id).organizationId,role:'viewer',expiresAt:Date.now()+3600000,mfaVerified:false}))}),{mode:0o600});
 return {root,password,tokens,cleanup:()=>rmSync(root,{recursive:true,force:true}),env:{
  NODE_ENV:'production',V79_HUB_STORE_BACKEND:'json',DATA_DIR:root,
  V79_HUB_ADMIN_PASSWORD:randomBytes(32).toString('hex'),V79_HUB_ADMIN_EMAIL:'vision79slu@gmail.com',
  V79_HUB_SECURITY_KEY:randomBytes(32).toString('hex'),V79_PLATFORM_SHARED_SECRET:randomBytes(32).toString('hex'),
  V79_REQUIRE_ADMIN_MFA:'1',V79_AGENT_API_TOKEN:'',V79_HELP_OLLAMA_URL:'',V79_HELP_OLLAMA_MODEL:'',
  WIPAY_ENABLED:'0',V79_TRIAL_REMINDER_LEADER:'0',V79_PASSWORD_RECOVERY_EMAIL_ENABLED:'0',V79_SENTINEL_HUB_SERVICE_ENABLED:'0',
  NODE_OPTIONS:'--import='+new URL('./isolated-env.mjs',import.meta.url).pathname,
 }};
}
