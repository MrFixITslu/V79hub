import express from 'express';
import fs from 'node:fs/promises';
import path from 'node:path';
import { GOOGLE_OWNER, GOOGLE_TIMEZONE } from './workforce-google.mjs';
import { runGoogleWorkOnce } from './workforce-google-worker.mjs';

export function projectGoogleThread(thread) {
  const all = Array.isArray(thread.messages) ? thread.messages : [];
  let partial = all.length > 20;
  const messages = all.slice(-20).map(message=>{
    const header = name => String(message.payload?.headers?.find(h=>h.name?.toLowerCase()===name)?.value || '').replace(/[\r\n]/g,' ').slice(0,500);
    const chunks=[];
    function visit(part, depth=0) {
      if (!part || depth>10) { partial=true;return; }
      if (part.mimeType==='text/plain' && typeof part.body?.data==='string') {
        const body=part.body.data;
        if(body.length>28000) partial=true;
        chunks.push(Buffer.from(body.slice(0,28000),'base64url').toString('utf8').slice(0,20000));
      }
      if (Array.isArray(part.parts)) {
        if(part.parts.length>20) partial=true;
        for(const child of part.parts.slice(0,20)) visit(child,depth+1);
      }
    }
    visit(message.payload);
    const text=chunks.join('\n').slice(0,20000);
    if(!text || chunks.join('\n').length>20000) partial=true;
    return {id:message.id,threadId:message.threadId,from:header('from'),replyTo:header('reply-to'),subject:header('subject'),date:header('date'),text};
  });
  return {id:thread.id,trust:'untrusted-email-content',partial,messages};
}

/** No credential values are returned by any route. The caller supplies trusted owner context. */
export function workforceGoogleRouter({ownerContext,sameOrigin,enabled,client,ledger,receiptDirectory,now=Date.now}) {
  const router=express.Router();
  router.use((req,res,next)=>{
    res.setHeader('Cache-Control','no-store');
    const owner=ownerContext(req);
    if(!owner) return res.status(403).json({error:'MFA-verified founder required'});
    req.googleOwner=owner;
    if(req.method!=='GET') {
      const mfa=req.user?.mfaVerifiedAt;
      if(!sameOrigin(req) || !Number.isFinite(mfa) || now()-mfa<0 || now()-mfa>300000) return res.status(403).json({error:'Fresh owner MFA and same origin required'});
    }
    next();
  });
  const wrap=fn=>async(req,res)=>{
    if(!enabled()) return res.status(503).json({error:'Google integration is disabled'});
    try {return await fn(req,res);}
    catch(error) {
      const code=/^GOOGLE_[A-Z_]+$/.test(error?.code||'')?error.code:'GOOGLE_REQUEST_REJECTED';
      return res.status(409).json({error:code});
    }
  };
  router.get('/status',async(_req,res)=>{
    if(!enabled()) return res.json({enabled:false,connected:false,account:GOOGLE_OWNER,timezone:GOOGLE_TIMEZONE,sendEnabled:false});
    try { return res.json({enabled:true,connected:true,...await client.status()}); }
    catch { return res.json({enabled:true,connected:false,account:GOOGLE_OWNER,timezone:GOOGLE_TIMEZONE,sendEnabled:false}); }
  });
  router.get('/inbox',wrap(async(req,res)=>{
    if(Object.keys(req.query).some(k=>!['query','pageToken'].includes(k))) throw new Error();
    return res.json(await client.listEmails(req.query.query??'in:inbox newer_than:7d',req.query.pageToken??''));
  }));
  router.get('/threads/:id',wrap(async(req,res)=>res.json(projectGoogleThread(await client.readThread(req.params.id)))));
  router.get('/appointments',wrap(async(req,res)=>{
    if(Object.keys(req.query).some(k=>!['start','end','pageToken'].includes(k))) throw new Error();
    const data=await client.listAppointments(req.query.start,req.query.end,req.query.pageToken??'');
    return res.json({timezone:GOOGLE_TIMEZONE,nextPageToken:data.nextPageToken??null,items:(data.items??[]).map(event=>({
      id:event.id,etag:event.etag,summary:event.summary??'',start:event.start,end:event.end,status:event.status,
      attendees:(event.attendees??[]).map(a=>({email:a.email,responseStatus:a.responseStatus})),
      organizer:event.organizer?.email??null,recurring:Boolean(event.recurringEventId || event.recurrence),
    }))});
  }));
  router.post('/run-once',wrap(async(req,res)=>{
    if(!req.body || Object.keys(req.body).length || !ledger || !receiptDirectory) throw new Error();
    const result=await runGoogleWorkOnce({ledger,client,enabled,ownerOrganizationId:req.googleOwner.organizationId,now,
      storeReceipt:async receipt=>{
        if(!/^[a-f0-9-]{36}$/.test(receipt.jobId)) throw new Error();
        await fs.mkdir(receiptDirectory,{recursive:true,mode:0o700});
        const file=path.join(receiptDirectory,receipt.jobId+'.json');
        const handle=await fs.open(file,'wx',0o600);
        try {await handle.writeFile(JSON.stringify(receipt));await handle.sync();} finally {await handle.close();}
        const parent=await fs.open(receiptDirectory,'r');try {await parent.sync();} finally {await parent.close();}
      }});
    return res.json(result);
  }));
  return router;
}

