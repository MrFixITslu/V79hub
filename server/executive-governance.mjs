import express from "express";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

// v1 governance-only policy registry. It does NOT dispatch or authorize tools.
// All actual actions still pass existing owner, MFA, G2, tenancy and destination policies.
export const V79_ORG = Object.freeze([
 {id:"founder",name:"Founder",reportsTo:null,skill:"Policy / Final Decisions",scope:"Sole authority over permission policy, payment, contracts and critical releases"},
 {id:"ceo",name:"AI CEO",reportsTo:"founder",skill:"Strategy",scope:"Strategy, risk, commercial prioritisation, executive reviews"},
 {id:"coo",name:"AI COO",reportsTo:"ceo",skill:"Operations",scope:"Delivery, workload, evidence, cross-department coordination"},
 {id:"marketing",name:"Head of Marketing",reportsTo:"coo",skill:"Marketing",scope:"Audience, brand, campaigns and lead quality"},
 {id:"technology",name:"Head of Technology",reportsTo:"coo",skill:"Technology",scope:"Engineering, security, reliability and change review"},
 {id:"sales",name:"Head of Sales",reportsTo:"coo",skill:"Sales",scope:"Qualification, consent-aware outreach, proposals and CRM"},
 {id:"finance",name:"Head of Finance",reportsTo:"coo",skill:"Finance",scope:"Cash flow, budgets, billing, forecasting and evidence"},
 {id:"customer-care",name:"Head of Customer Care",reportsTo:"coo",skill:"Customer Care",scope:"Customer complaints, first-response quality, Tiquet intake, resolution and follow-up"}
]);

export const V79_POLICY_ACTIONS = Object.freeze([
 {id:"monitor",label:"Read system health and generate alerts",department:"technology",approvalRequired:false,locked:false,capability:"read-only",execution:"Existing monitoring systems; not granted by this page"},
 {id:"draft_marketing",label:"Prepare social posts and campaign drafts",department:"marketing",approvalRequired:false,locked:false,capability:"draft",execution:"Draft only; no public publishing permission granted"},
 {id:"campaign_ideas",label:"Prepare three Marketing + Sales sales-drive ideas",department:"marketing",approvalRequired:false,locked:false,capability:"draft",execution:"Recommendation only; CEO/COO review before execution"},
 {id:"draft_intro",label:"Prepare introductory emails for qualified leads",department:"sales",approvalRequired:false,locked:false,capability:"draft",execution:"Only drafts; owner manually sends"},
 {id:"lead_qualification",label:"Qualify opted-in enquiries using approved CRM data",department:"sales",approvalRequired:false,locked:false,capability:"read-only",execution:"Existing CRM permissions still apply"},
 {id:"finance_reports",label:"Produce financial forecasts and reports",department:"finance",approvalRequired:false,locked:false,capability:"read-only",execution:"Read-only, evidence required"},
 {id:"post_publish",label:"Publish a previously approved campaign post",department:"marketing",approvalRequired:false,locked:false,capability:"guarded",execution:"No autonomous publishing adapter is connected by this policy page"},
 {id:"routine_restart",label:"Perform a pre-authorised safe service restart",department:"technology",approvalRequired:true,locked:false,capability:"guarded",execution:"Requires independently tested allowlist and rollback; not wired"},
 {id:"code_release",label:"Deploy application or security code changes",department:"technology",approvalRequired:true,locked:true,capability:"owner",execution:"Owner approval, change gate and independent verification always required"},
 {id:"customer_send",label:"Send customer or prospect emails",department:"sales",approvalRequired:true,locked:true,capability:"owner",execution:"Drafts only until founder explicitly sends"},
 {id:"money",label:"Spend money, authorise refunds or bank transfers",department:"finance",approvalRequired:true,locked:true,capability:"owner",execution:"No autonomous payments or spending"},
 {id:"pricing_contracts",label:"Change customer pricing, contracts or subscriptions",department:"sales",approvalRequired:true,locked:true,capability:"owner",execution:"Founder-controlled"},
 {id:"policy_access",label:"Change security rules, worker permissions or MFA",department:"technology",approvalRequired:true,locked:true,capability:"owner",execution:"Cannot be delegated via the workforce"}
]);

export const V79_CAMPAIGNS = Object.freeze([
 {id:"ai-readiness",name:"Caribbean AI Readiness Check",audience:"SMEs exploring AI",channel:"LinkedIn, Facebook and website",offer:"Free educational readiness checklist and invitation to a consultation",scores:{audience:5,fit:5,value:4,cost:4,risk:4},risk:"Claims must be backed by a documented assessment; avoid guaranteed savings"},
 {id:"resilience",name:"Business Continuity Health Check",audience:"SMEs reliant on email, Wi-Fi and cloud",channel:"Email opt-ins, LinkedIn and website",offer:"Practical backup and network-resilience checklist",scores:{audience:4,fit:5,value:4,cost:4,risk:5},risk:"Never imply an audit or security certification was completed"},
 {id:"tiquet-demo",name:"Tiquet Customer Support Demo",audience:"Service businesses managing enquiries",channel:"Existing inbound leads, website demos and social posts",offer:"A walkthrough of support ticket workflows",scores:{audience:3,fit:4,value:5,cost:4,risk:4},risk:"Avoid promises about product functions that have not been verified live"}
]);
export const V79_SCORE_WEIGHTS=Object.freeze({audience:0.30,fit:0.25,value:0.20,cost:0.15,risk:0.10});
export function rankCampaigns(campaigns=V79_CAMPAIGNS){
 return campaigns.map(c=>({...c,score:Object.entries(V79_SCORE_WEIGHTS).reduce((n,[key,w])=>n+(c.scores[key]||0)*w,0)}))
 .sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id));
}
export const V79_MEETING=Object.freeze({frequency:"weekly",weekday:"Friday",time:"06:00",timezone:"America/St_Lucia",firstScheduled:"2026-11-13T06:00:00-04:00",format:"Five HOD updates → COO coordination → CEO review → Marketing+Sales choice → owner briefing"});

const MAX_FILE=160*1024;
const fail=(message,status=400)=>Object.assign(new Error(message),{status});
const exact=(x,keys)=>x && typeof x==="object" && !Array.isArray(x) &&
 Object.keys(x).sort().join("|") === [...keys].sort().join("|");
const actionById=id=>V79_POLICY_ACTIONS.find(x=>x.id===id);
const basicState=()=>({schema:1,revision:0,decisions:Object.fromEntries(V79_POLICY_ACTIONS.map(a=>[a.id,a.approvalRequired])),audit:[]});
export function createExecutiveGovernanceStore({file,secret,now=()=>new Date()}){
 if(typeof file!=="string"||!path.isAbsolute(file)||typeof secret!=="string"||Buffer.byteLength(secret)<32)throw Error("Absolute file and independent signing secret required");
 const dir=path.dirname(file);
 const sign=state=>crypto.createHmac("sha256",secret).update("v79-executive-policy-v1\0"+JSON.stringify(state)).digest("hex");
 function load(){
  let fd;
  try{fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);}
  catch(e){if(e.code==="ENOENT")return basicState();throw e;}
  try{
   if(fs.fstatSync(fd).size>MAX_FILE)throw fail("Governance policy too large",503);
   const input=JSON.parse(fs.readFileSync(fd,"utf8"));
   if(!input?.state||typeof input.mac!=="string"||!/^[a-f0-9]{64}$/.test(input.mac))throw fail("Governance policy integrity invalid",503);
   const actual=Buffer.from(input.mac,"hex"),expected=Buffer.from(sign(input.state),"hex");
   if(!crypto.timingSafeEqual(actual,expected))throw fail("Governance policy signature invalid",503);
   const state=input.state;
   if(state.schema!==1||!Number.isSafeInteger(state.revision)||state.revision<0||!Array.isArray(state.audit)||state.audit.length>250||
      !exact(state.decisions,V79_POLICY_ACTIONS.map(x=>x.id))||V79_POLICY_ACTIONS.some(a=>typeof state.decisions[a.id]!=="boolean"||(a.locked&&!state.decisions[a.id])))throw fail("Governance policy schema mismatch",503);
   return state;
  }finally{fs.closeSync(fd)}
 }
 function save(state){
  fs.mkdirSync(dir,{recursive:true,mode:0o700});
  const lock=file+".lock";let locked=false;let tmp="";
  try{
   fs.mkdirSync(lock,{mode:0o700});locked=true;
   const latest=load();
   if(latest.revision!==state.expectedRevision)throw fail("Governance policy revision changed; refresh",409);
   const next={schema:1,revision:latest.revision+1,decisions:{...latest.decisions,[state.id]:state.approvalRequired},
     audit:[...latest.audit,{at:now().toISOString(),id:state.id,approvalRequired:state.approvalRequired,actor:state.actor}].slice(-200)};
   tmp=file+".tmp."+process.pid+"."+crypto.randomBytes(5).toString("hex");
   const fd=fs.openSync(tmp,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_NOFOLLOW,0o600);
   try{fs.writeFileSync(fd,JSON.stringify({state:next,mac:sign(next)}));fs.fsyncSync(fd);}
   finally{fs.closeSync(fd);}
   fs.renameSync(tmp,file);tmp="";
   return next;
  }finally{if(tmp)try{fs.unlinkSync(tmp)}catch{};if(locked)fs.rmdirSync(lock)}
 }
 return Object.freeze({
  list:()=>load(),
  update(input,actor){
   if(!exact(input,["id","approvalRequired","expectedRevision"])||typeof actor!=="string"||actor.length<1||actor.length>160)throw fail("Invalid policy request");
   const a=actionById(input.id);
   if(!a||typeof input.approvalRequired!=="boolean"||!Number.isSafeInteger(input.expectedRevision)||input.expectedRevision<0)throw fail("Unknown policy or invalid value");
   if(a.locked&&!input.approvalRequired)throw fail("Mandatory founder approval cannot be disabled",403);
   return save({...input,actor});
  }
 });
}

export function createExecutiveGovernanceRouter({store,ownerContext,freshOwnerContext,sameOrigin,enabled=()=>false}){
 if(!store||typeof ownerContext!=="function"||typeof freshOwnerContext!=="function"||typeof sameOrigin!=="function")throw Error("Required guarded governance dependencies missing");
 const router=express.Router();
 router.use((req,res,next)=>{
  res.setHeader("Cache-Control","no-store");
  if(!enabled())return res.status(503).json({error:"Executive Governance is not enabled"});
  const owner=ownerContext(req);
  if(!owner)return res.status(403).json({error:"MFA-verified founder access required"});
  req.v79Owner=owner;
  next();
 });
 router.get("/",(req,res)=>{
  try{res.json({status:"governance-only",executionWired:false,workersActivated:false,
    note:"Approval preferences are not tool permissions. Existing MFA, G2 and app-specific gates still control execution.",
    roles:V79_ORG,meeting:V79_MEETING,actions:V79_POLICY_ACTIONS,
    campaigns:rankCampaigns(),suggestedCampaign:"ai-readiness",
    campaignDecision:"Candidate based on illustrative scoring; final selection requires verified evidence and CEO/COO review.",
    policy:store.list()});}
  catch{res.status(503).json({error:"Signed governance policy could not be verified"})}
 });
 router.post("/policy",(req,res)=>{
  if(!sameOrigin(req))return res.status(403).json({error:"Same-origin required"});
  if(!freshOwnerContext(req))return res.status(403).json({error:"Fresh founder MFA required to change approval preferences"});
  try{res.json({policy:store.update(req.body,req.v79Owner.userId),
    status:"preferences-saved",executionWired:false});}
  catch(e){res.status([400,403,409,503].includes(e.status)?e.status:503).json({error:e.status?e.message:"Policy storage failed"})}
 });
 return router;
}
