import express from 'express';
import { randomUUID } from 'node:crypto';
export const STEP_UP_MS=300000;
export function rotateVerifiedSession({sessions,oldKey,oldSession,userId,at,persist,makeToken,hashToken}) {
  if(!oldSession||sessions.get(oldKey)!==oldSession||oldSession.userId!==userId||!oldSession.mfaVerified||!Number.isFinite(at)||oldSession.expiresAt<=at)throw Error('Session changed');
  const token=makeToken(),key=hashToken(token);if(key===oldKey||sessions.has(key))throw Error('Session collision');
  const next={...oldSession,mfaVerified:true,mfaVerifiedAt:at};sessions.set(key,next);sessions.delete(oldKey);
  try{persist()}catch(error){sessions.delete(key);sessions.set(oldKey,oldSession);throw error}
  return {token,expiresAt:next.expiresAt};
}
export function createOwnerStepUpRouter({ownerContext,binding,session,verifyCode,rotate,sameOrigin,now=Date.now}) {
  const router=express.Router(), pending=new Map(), attempts=new Map();
  const clean=()=>{const t=now();for(const [k,v] of pending)if(v.expires<=t)pending.delete(k);for(const [k,v] of attempts)if(v.until<=t)attempts.delete(k)};
  router.use((req,res,next)=>{res.setHeader('Cache-Control','no-store');if(!sameOrigin(req))return res.status(403).json({error:'Same-origin request required'});const owner=ownerContext(req),key=binding(req),s=session(req);if(!owner||!key||!s||!s.mfaVerified||!Number.isFinite(s.expiresAt)||s.expiresAt<=now())return res.status(403).json({error:'Sign in with your MFA-verified owner account.'});req.stepUp={owner,key,s};clean();if((attempts.get(key)?.count||0)>=5)return res.status(429).json({error:'Too many verification attempts. Try again in ten minutes.'});next()});
  router.post('/challenge',(req,res)=>{const {key,s}=req.stepUp;const t=now();if(Number.isFinite(s.mfaVerifiedAt)&&s.mfaVerifiedAt<=t&&t-s.mfaVerifiedAt<=STEP_UP_MS)return res.json({fresh:true,expiresAt:s.mfaVerifiedAt+STEP_UP_MS});if(pending.size>=1000)return res.status(503).json({error:'Verification is temporarily busy. Try again shortly.'});for(const [id,v]of pending)if(v.key===key)pending.delete(id);const id=randomUUID();pending.set(id,{key,expires:t+120000});return res.json({fresh:false,challengeId:id,expiresAt:t+120000})});
  router.post('/complete',async(req,res)=>{const {key,owner}=req.stepUp;const {challengeId,code}=req.body||{};if(!req.body||Object.keys(req.body).sort().join(',')!=='challengeId,code'||typeof challengeId!=='string'||typeof code!=='string'||!/^\d{6}$/.test(code))return res.status(400).json({error:'Enter the six-digit authenticator code.'});const c=pending.get(challengeId);if(!c||c.key!==key||c.expires<=now())return res.status(401).json({error:'Verification expired. Reopen the verification prompt.'});const at=now(),prior=attempts.get(key);attempts.set(key,{count:(prior?.count||0)+1,until:prior?.until||at+600000});
    try{if(!await verifyCode(req,owner,code))return res.status(401).json({error:'That code was not accepted. Use the current code from your authenticator.'});if(pending.get(challengeId)!==c)return res.status(409).json({error:'Verification was already used. Refresh the action status.'});pending.delete(challengeId);await rotate(req,res,owner,key,at);attempts.delete(key);return res.json({verified:true,expiresAt:at+STEP_UP_MS})}catch{return res.status(503).json({error:'Verification could not be saved. Your action has not been retried.'})}
  });
  return router;
}
