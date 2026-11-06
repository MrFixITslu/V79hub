import crypto from 'node:crypto';
import {signPlatformRequest} from './platform-contract.mjs';

export const HELP_SUPPORT_PATH='/api/integrations/hub-help/v1/tickets';
const APPS=new Set(['all','hub','tiquet','pos','ffpro','marketing','academy','combatzone']);
const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
export class HelpTicketError extends Error {constructor(message,status=503){super(message);this.status=status;}}
export function validateHelpTicket(body){
  if(!body||typeof body!=='object'||Array.isArray(body)||Object.keys(body).sort().join(',')!=='app,idempotencyKey,kind,summary')return 'Review the support request and try again.';
  if(!UUID.test(body.idempotencyKey)||!APPS.has(body.app)||!['unresolved','error'].includes(body.kind))return 'Choose an app and issue type, then try again.';
  if(typeof body.summary!=='string'||body.summary.trim().length<20||body.summary.length>18000||/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(body.summary))return 'The reviewed summary must contain 20–18,000 characters without control characters.';
  return null;
}
/** @param {{env?:NodeJS.ProcessEnv,identity?:(actor:{userId:string,organizationId:string})=>({name:string,email:string,workspace:string}|null),fetcher?:typeof fetch,clock?:()=>number}} options */
export function createHelpTicketBridge({env=process.env,identity,fetcher=globalThis.fetch,clock=Date.now}={}){
  let endpoint,secret=env.V79_HELP_SUPPORT_SHARED_SECRET||'';
  try{
    const url=new URL(env.V79_HELP_SUPPORT_TIQUET_URL||'');
    const internal=['v79-tiquet-manager','127.0.0.1','localhost','[::1]'].includes(url.hostname);
    if(url.username||url.password||url.search||url.hash||url.pathname!=='/'||url.protocol!=='https:'&&!(url.protocol==='http:'&&internal))throw Error();
    endpoint=new URL(HELP_SUPPORT_PATH,url).href;
  }catch{}
  const enabled=env.V79_HELP_SUPPORT_ENABLED==='1'&&Boolean(endpoint)&&Buffer.byteLength(secret)>=48&&typeof identity==='function';
  return {enabled,async submit(body,actor){
    if(!enabled)throw new HelpTicketError('Ticket submission is unavailable. Copy your summary and contact V79 support.');
    const invalid=validateHelpTicket(body);if(invalid)throw new HelpTicketError(invalid,400);
    const contact=identity(actor);
    if(!contact||typeof contact.name!=='string'||typeof contact.workspace!=='string'||!/^\S+@\S+\.\S+$/.test(contact.email||''))throw new HelpTicketError('Your Hub contact details are unavailable. Contact V79 support.',403);
    const requestId=crypto.createHmac('sha256',secret).update(JSON.stringify(['hub-help-v1',actor.organizationId,actor.userId,body.idempotencyKey])).digest('hex');
    const payload=JSON.stringify({schemaVersion:1,requestId,requester:{organizationId:actor.organizationId,userId:actor.userId,name:contact.name,email:contact.email,workspace:contact.workspace},app:body.app,kind:body.kind,summary:body.summary});
    if(Buffer.byteLength(payload)>32000)throw new HelpTicketError('Your summary is too large. Shorten it and try again.',400);
    const timestamp=String(clock()),signature=signPlatformRequest({method:'POST',pathname:HELP_SUPPORT_PATH,timestamp,body:payload,secret});
    let response,data;
    try{
      response=await fetcher(endpoint,{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{'content-type':'application/json','x-v79-service-id':'v79-hub-help','x-v79-timestamp':timestamp,'x-v79-signature':signature},body:payload});
      // Never reflect internal errors, destination identities or unbounded responses.
      const decoder=new TextDecoder();const reader=response.body?.getReader();let raw='',bytes=0;
      if(!reader)throw Error();
      try{for(;;){const {done,value}=await reader.read();if(done)break;bytes+=value.byteLength;if(bytes>2048)throw Error();raw+=decoder.decode(value,{stream:true});}}finally{await reader.cancel().catch(()=>{});}
      data=JSON.parse(raw);
    }catch{throw new HelpTicketError('Tiquet has not confirmed receipt. Keep this draft open and retry the same request.');}
    if(response.status===409)throw new HelpTicketError('This request has different saved details. Contact V79 support with your copied summary.',409);
    if(response.status===410)throw new HelpTicketError('The previous ticket was removed from Tiquet. Contact V79 support with your copied summary; retry will not create another ticket.',410);
    if(response.status===429)throw new HelpTicketError('Please wait before retrying this request. Your draft is still here.',429);
    if(![200,201].includes(response.status)||data?.accepted!==true||data.requestId!==requestId||typeof data.reference!=='string'||!/^HELP-[a-f0-9-]{36}$/i.test(data.reference)||data.priority!=='high')throw new HelpTicketError('Tiquet has not confirmed receipt. Keep this draft open and retry the same request.');
    return {submitted:true,reference:data.reference,priority:'high'};
  }};
}
