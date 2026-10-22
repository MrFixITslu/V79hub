import fs from 'node:fs/promises';
import path from 'node:path';
import {constants} from 'node:fs';
import {createHmac,timingSafeEqual,randomUUID} from 'node:crypto';
export function createPricingRequestStore({file,secret}){
 const canonical=s=>JSON.stringify(s,(_k,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
 const mac=s=>{if(typeof secret!=='string'||secret.length<24)throw Error('Pricing ledger key unavailable');return createHmac('sha256',secret).update(canonical(s)).digest('hex')};
 const empty=()=>({version:1,requests:[],events:[]});
 async function read(){
  mac(empty());let handle;
  try{
   handle=await fs.open(file,constants.O_RDONLY|constants.O_NOFOLLOW);const stat=await handle.stat();
   if(!stat.isFile()||stat.size>20*1024*1024||(stat.mode&0o077))throw Error('Pricing ledger metadata invalid');
   const envelope=JSON.parse(await handle.readFile('utf8')),s=envelope.state;
   if(!s||s.version!==1||!Array.isArray(s.requests)||!Array.isArray(s.events)||s.requests.length>5000||s.events.length>15000||!/^[a-f0-9]{64}$/.test(envelope.mac||'')||!timingSafeEqual(Buffer.from(mac(s)),Buffer.from(envelope.mac)))throw Error('Pricing ledger integrity failure');
   return structuredClone(s);
  }catch(e){if(e.code==='ENOENT')return empty();throw e}finally{await handle?.close()}
 }
 async function transact(fn){
  mac(empty());await fs.mkdir(path.dirname(file),{recursive:true,mode:0o700});const lock=file+'.lock';await fs.mkdir(lock,{mode:0o700});let temp;
  try{
   const state=await read(),result=await fn(state);if(state.events.length>15000)throw Error('Pricing audit capacity reached');
   temp=file+'.'+randomUUID()+'.tmp';const h=await fs.open(temp,constants.O_CREAT|constants.O_EXCL|constants.O_WRONLY|constants.O_NOFOLLOW,0o600);
   try{await h.writeFile(JSON.stringify({state,mac:mac(state)}));await h.sync()}finally{await h.close()}
   await fs.rename(temp,file);temp=null;const parent=await fs.open(path.dirname(file),'r');try{await parent.sync()}finally{await parent.close()}
   return structuredClone(result);
  }finally{if(temp)await fs.unlink(temp).catch(()=>{});await fs.rmdir(lock)}
 }
 return {read,transact};
}
