import express from "express";
import {timingSafeEqual} from "node:crypto";
// Read-only, internal, least-privilege interface for scheduled local jobs.
// The existing G2 worker token is required; no cookie/origin traffic allowed.
// Only approved, digest-pinned SKILL.md guidance is returned, never code or ZIP.
export function scheduledSkillRouter({packages,enabled,workerToken}){
 const router=express.Router();
 router.use((_req,res,next)=>{
   res.setHeader("Cache-Control","no-store");
   if(!enabled()||!packages)return res.status(503).json({error:"Scheduled guidance unavailable"});
   next();
 });
 router.get("/:job",(req,res)=>{
   const expected=String(workerToken()||"");
   const supplied=String(req.get("x-v79-workforce-token")||"");
   if(req.get("origin")||req.get("cookie")||expected.length<32||
       Buffer.byteLength(expected)!==Buffer.byteLength(supplied)||
       !timingSafeEqual(Buffer.from(expected),Buffer.from(supplied)))
     return res.status(403).json({error:"Trusted scheduled worker required"});
   try{
     const result=packages.scheduledSnapshot(req.params.job);
     if(result.packages.length>2)return res.status(503).json({error:"Scheduled guidance limit exceeded"});
     return res.json(result);
   }catch(e){
     return res.status(Number.isSafeInteger(e?.status)?e.status:503)
       .json({error:"Scheduled skill profile unavailable"});
   }
 });
 return router;
}
