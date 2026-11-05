import express from 'express';
import {timingSafeEqual} from 'node:crypto';
const REQUEST=/^[A-Za-z0-9_-]{43}$/;
const ORIGIN='https://evidence.v79sl.com';
const ESC=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function registerEvidenceGatewayBridge(app,{ownerMfaContext,sameOrigin,readBridgeToken,ownerActive,ownerSubject,gatewayBaseUrl,fetchImpl=fetch,now=Date.now}){
 const base=new URL(gatewayBaseUrl);
 if(base.protocol!=='http:'||!/^172\.(?:1[6-9]|2\d|3[01])\.\d+\.1$/.test(base.hostname)||base.port!=='8765'||base.pathname!=='/'||base.username||base.password||base.search||base.hash)throw Error('Invalid private Gateway broker');
 const configured=()=>{try{return readBridgeToken()||'';}catch{return '';}};
 const headers=res=>{res.setHeader('Cache-Control','no-store');res.setHeader('Referrer-Policy','same-origin');res.setHeader('X-Frame-Options','DENY');res.setHeader('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://chatgpt.com; frame-ancestors 'none'; base-uri 'none'");};
 const fresh=req=>{const at=req.user?.mfaVerifiedAt;return Number.isFinite(at)&&now()-at>=0&&now()-at<=300000;};
 async function call(path,body){
  const token=configured();if(token.length<32)throw Error('Gateway not configured');
  const response=await fetchImpl(new URL(path,base),{method:body===undefined?'GET':'POST',headers:{'x-v79-gateway-internal':token,'content-type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),redirect:'error',signal:AbortSignal.timeout(7000)});
  const text=await response.text();if(!response.ok||Buffer.byteLength(text)>8192)throw Error('Gateway unavailable');return JSON.parse(text);
 }
 function page(res,content){headers(res);return res.type('html').send('<!doctype html><html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><title>V79 Evidence Gateway access</title><style>body{font:17px system-ui;background:#f5f7fa;color:#17212e;margin:0;padding:30px}main{max-width:650px;background:white;margin:8vh auto;padding:32px;border:1px solid #dce3eb;border-radius:18px}h1{font-size:28px}p{line-height:1.6}button,a{display:inline-block;padding:14px 20px;margin:8px 8px 0 0}button{font:inherit;border:1px solid #087c89;border-radius:8px;background:#087c89;color:white}button.secondary{background:white;color:#17212e}small{overflow-wrap:anywhere}</style><main>'+content+'</main></html>');}
 app.get('/internal/evidence-gateway/owner-active',(req,res)=>{
  res.setHeader('Cache-Control','no-store');const expected=configured();const received=String(req.get('x-v79-gateway-internal')||'');
  if(req.get('origin')||req.get('cookie')||expected.length<32||received.length!==expected.length||Buffer.byteLength(received)!==Buffer.byteLength(expected)||!timingSafeEqual(Buffer.from(received),Buffer.from(expected)))return res.status(403).json({active:false});
  return res.json({active:ownerActive()===true});
 });
 app.get('/api/agent/evidence-gateway/authorize',async(req,res)=>{
  if(!ownerMfaContext(req))return res.status(403).json({error:'Sign in with the MFA-verified V79 owner account first'});
  const id=String(req.query.request||'');if(!REQUEST.test(id))return res.status(400).json({error:'Invalid consent request'});
  try{
   const info=await call('/internal/request?request='+encodeURIComponent(id));
   if(info.requestId!==id||info.resource!==ORIGIN+'/mcp'||info.scope!=='evidence:read'||!/^[a-f0-9]{64}$/.test(info.clientIdHash))throw Error('Invalid consent binding');
   return page(res,'<h1>Connect V79 Evidence Gateway</h1><p>This grants the requesting MCP client <strong>read-only evidence access for up to 24 hours</strong>. Access tokens expire after 15 minutes. You can revoke access at any time.</p><p>It can read dated host/service observations and supplied release, backup and readiness evidence. Missing evidence stays unknown. It cannot run commands, access databases, send messages, change apps or control Sentinel.</p><small>Client fingerprint: '+ESC(info.clientIdHash)+'</small>'+(!fresh(req)?'<p><strong>A fresh Hub MFA sign-in is required before approval.</strong> Sign in to Hub again, then restart the connection.</p>':'<form method="post" action="/api/agent/evidence-gateway/authorize"><input type="hidden" name="requestId" value="'+ESC(id)+'"><button name="approved" value="true">Allow read-only connection</button><button class="secondary" name="approved" value="false">Deny</button></form>'));
  }catch{return res.status(503).json({error:'Gateway consent request unavailable or expired'});}
 });
 app.post('/api/agent/evidence-gateway/authorize',express.urlencoded({extended:false,limit:'2kb'}),async(req,res)=>{
  const context=ownerMfaContext(req);if(!context||!fresh(req)||!sameOrigin(req))return res.status(403).json({error:'Fresh owner MFA and same-origin consent required'});
  if(!req.body||Object.keys(req.body).sort().join(',')!=='approved,requestId'||!REQUEST.test(req.body.requestId)||!['true','false'].includes(req.body.approved))return res.status(400).json({error:'Invalid consent'});
  try{const data=await call('/internal/consent',{requestId:req.body.requestId,subject:ownerSubject(),approved:req.body.approved==='true'});const redirect=new URL(data.redirect);
   if(redirect.protocol!=='https:'||redirect.host!=='chatgpt.com'||!(redirect.pathname==='/connector_platform_oauth_redirect'||/^\/connector\/oauth\/[A-Za-z0-9_-]{8,160}$/.test(redirect.pathname))||redirect.hash)throw Error('Invalid callback');
   headers(res);return res.redirect(303,redirect.href);
  }catch{return page(res.status(409),'<h1>Restart the connection</h1><p>This consent request could not be completed. It may have expired or already been submitted. Return to ChatGPT and start the Evidence Gateway connection again.</p><p>Submit the new approval once. This page does not confirm whether ChatGPT connected.</p>');}
 });
 app.get('/api/agent/evidence-gateway/access',async(req,res)=>{
  if(!ownerMfaContext(req))return res.status(403).json({error:'MFA-verified owner access required'});
  return page(res,'<h1>V79 Evidence Gateway</h1><p>Standalone, read-only MCP service.</p><p>MCP endpoint: <strong>https://evidence.v79sl.com/mcp</strong></p><p>Authentication: OAuth. Connecting a client opens your Hub owner-consent page. Sentinel remains outside this connection.</p><form method="post" action="/api/agent/evidence-gateway/revoke"><button class="secondary" name="confirmation" value="REVOKE_GATEWAY_ACCESS">Revoke all Gateway connections</button></form><p>Revocation requires a fresh owner MFA session.</p>');
 });
 app.post('/api/agent/evidence-gateway/revoke',express.urlencoded({extended:false,limit:'2kb'}),async(req,res)=>{
  if(!ownerMfaContext(req)||!fresh(req)||!sameOrigin(req))return res.status(403).json({error:'Fresh owner MFA and same-origin request required'});
  if(!req.body||Object.keys(req.body).join(',')!=='confirmation'||req.body.confirmation!=='REVOKE_GATEWAY_ACCESS')return res.status(400).json({error:'Exact revocation required'});
  try{await call('/internal/revoke',{subject:ownerSubject()});return page(res,'<h1>Gateway access revoked</h1><p>Existing Gateway access and refresh tokens can no longer be used. New access requires a new owner consent.</p>');}
  catch{return res.status(503).json({error:'Revocation not confirmed. Disable the Gateway service if urgent.'});}
 });
}
