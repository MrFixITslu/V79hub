from pathlib import Path
import subprocess,json,hashlib,re
root=Path('/home/firelion/.v79-production-readiness-20261107');root.mkdir(exist_ok=True,mode=0o700)
expected='sha256:e605371a5ee8125fbaf73670fd6722811d9ac20eb3f870bbb339c4c5f0a83ecb'
live=json.loads(subprocess.check_output(['docker','inspect','v79-hub']))[0]
assert live['Image']==expected,'Live baseline changed; reconcile first'
release=root/'hub-release';(release/'server').mkdir(parents=True,exist_ok=True);(release/'dist/assets').mkdir(parents=True,exist_ok=True)
def read(path):return subprocess.check_output(['docker','exec','v79-hub','cat',path],text=True)
def once(t,a,b):assert t.count(a)==1, 'Unexpected patch anchor: '+a[:50];return t.replace(a,b,1)
server=read('/app/server.ts');original_server=server
server=once(server,'import { workforceActionRouters } from "./server/workforce-action-routes.mjs";','import { workforceActionRouters } from "./server/workforce-action-routes.mjs";\nimport { createOwnerStepUpRouter, rotateVerifiedSession } from "./server/owner-step-up.mjs";')
route='''app.use("/api/security/mfa/step-up", requireAuth, createOwnerStepUpRouter({
  ownerContext: ownerApprovalContext,
  binding: (req:Request) => { const auth=req.headers.authorization; const token=auth?.startsWith("Bearer ")?auth.slice(7):cookieToken(req.headers.cookie);return token?sessionKey(token):null; },
  session: (req:Request)=>(req as any).user,
  sameOrigin:sameOriginMutation,
  verifyCode: async (_req:Request,owner:any,code:string)=>{const user=store.users.find(u=>u.id===owner.userId);if(!user?.mfaEnabled||!user.mfaSecretEnc)return false;return verifyTotp(decryptTotpSecret(user.mfaSecretEnc,hubSecurityKey),code,Date.now(),2);},
  rotate: async (req:Request,res:Response,owner:any,oldKey:string,at:number)=>{
    const old=sessions.get(oldKey);if(!old||old!==(req as any).user||!ownerApprovalContext(req)||old.userId!==owner.userId||old.expiresAt<=at)throw Error("Session changed");
    const next=rotateVerifiedSession({sessions,oldKey,oldSession:old,userId:owner.userId,at,persist:persistSessions,makeToken:()=>"v79_tok_"+crypto.randomBytes(24).toString("hex"),hashToken:sessionKey});
    res.setHeader("Set-Cookie",sessionCookie(next.token,Math.max(0,Math.floor((next.expiresAt-at)/1000))));
  },
}));
'''
server=once(server,'app.get("/api/security/mfa/status", requireAuth, (req, res) => {',route+'\napp.get("/api/security/mfa/status", requireAuth, (req, res) => {')
(release/'server.ts').write_text(server)
actions=read('/app/server/workforce-action-routes.mjs');original_actions=actions
old='catch (e) { if(e?.code==="REVIEW_MFA_REQUIRED")return res.status(403).json({error:"Complete a fresh owner MFA challenge, then approve this exact specialist review."}); return res.status(409).json({ error: "Action rejected or storage unavailable. Refresh and verify the current state before retrying." }); }'
new='''catch (e) {
      if(e?.code==="REVIEW_MFA_REQUIRED")return res.status(403).json({code:"FRESH_MFA_REQUIRED",error:"Refresh owner MFA verification to approve this exact review."});
      if(e?.message==="Action revision conflict")return res.status(409).json({code:"ACTION_CHANGED",error:"This action changed since it was displayed. Refresh status and review its current state."});
      if(e?.message==="Work item requires current approval")return res.status(409).json({code:"CURRENT_APPROVAL_REQUIRED",error:"This action needs a current unused approval. Refresh status; an expired or completed action cannot be executed again."});
      if(e?.message==="Action cannot be approved")return res.status(409).json({code:"APPROVAL_STATE_CHANGED",error:"The action is no longer awaiting this decision. Refresh status and review the current scope."});
      if(["EACCES","EROFS","ENOSPC","ECONNREFUSED","57P01","53300"].includes(e?.code))return res.status(503).json({code:"STORAGE_UNAVAILABLE",error:"Action storage is temporarily unavailable. No success is confirmed; check status before retrying."});
      return res.status(409).json({code:"ACTION_NOT_COMPLETED",error:"This action was not completed. Refresh its current status before retrying."});
    }'''
actions=once(actions,old,new);(release/'server/workforce-action-routes.mjs').write_text(actions)
index=read('/app/dist/index.html');original_index=index
asset=re.findall(r'<script[^>]+src="(/assets/[^\"]+\.js)"',index)[0];bundle=read('/app/dist'+asset);original_bundle=bundle
start=bundle.index('function Nm(');end=bundle.index('var ',start+23000) if 'var ' in bundle[start+23000:] else len(bundle)
section=bundle[start:end]
section=once(section,'se=(0,b.useRef)(null),W=r&&','se=(0,b.useRef)(null),uxMutationError=(0,b.useRef)(false),W=r&&')
section=once(section,'y(t.jobs),O(new Date),E(``)','y(t.jobs),O(new Date),uxMutationError.current||E(``)')
section=once(section,'y([]),d([]),h(!1),s(!1),O(null),E(t instanceof Error?t.message:`Action queue unavailable`)','s(!1),O(null),uxMutationError.current||E(t instanceof Error?t.message:`Action queue unavailable`)')
section=once(section,'S(!0),E(``),A(``);try{await e(),await ce()}catch(e){E(e instanceof Error?e.message:`Action unavailable`),y([]),d([]),h(!1),s(!1),O(null)}','S(!0),uxMutationError.current=!1,E(``),A(``);try{await e(),await ce()}catch(e){try{await ce()}catch{}uxMutationError.current=!0,E(e instanceof Error?e.message:`Action unavailable`)}')
bundle=bundle[:start]+section+bundle[end:]
name='index-V79Readiness20261107.js';(release/'dist/assets'/name).write_text(bundle)
index=once(index,asset,'/assets/'+name);index=once(index,'</head>','<script src="/owner-step-up-client.js" defer></script></head>');(release/'dist/index.html').write_text(index)
for src,dst in [('owner-step-up.mjs','server/owner-step-up.mjs'),('owner-step-up-client.js','dist/owner-step-up-client.js')]:
 (release/dst).write_bytes((root/src).read_bytes())
container='''FROM localhost/v79-readiness-hub-base:20261107
COPY server.ts /app/server.ts
COPY server/ /app/server/
COPY dist/ /app/dist/
''';(release/'Dockerfile').write_text(container)
before={p:hashlib.sha256(t.encode()).hexdigest() for p,t in [('server.ts',original_server),('server/workforce-action-routes.mjs',original_actions),('dist/index.html',original_index),(asset,original_bundle)]}
manifest={'expected_image':expected,'original_files':before,'changed_files':{str(p.relative_to(release)):hashlib.sha256(p.read_bytes()).hexdigest() for p in release.rglob('*') if p.is_file()},'scope':'Owner step-up MFA; existing five-minute limit retained; stable action errors and last verified queue retained. No business data, entitlement or approval ledger changes.'}
(root/'hub-release-manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps({'prepared':True,'files':len(manifest['changed_files']),'baseline':expected}))
