// Run only for a local visual review. Synthetic customer, ephemeral storage,
// isolated outbound fetch and no real app credentials or publishing actions.
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';
import {verifyPlatformRequest} from '../server/platform-contract.mjs';
import {fileURLToPath} from 'node:url';
import {createServer,request} from 'node:http';
import {helpFixture} from './customer-help-fixture.mjs';
const ownerPreview=process.argv.includes('--owner');
const fixture=helpFixture({ownerMfa:ownerPreview});
// Visual-only receipt simulator; actual PostgreSQL integration is verified separately.
const supportPreview=process.argv.includes('--support');
let supportServer=null;
if(supportPreview){
 const secret=crypto.randomBytes(48).toString('hex'),receipts=new Map();
 supportServer=createServer(async(req,res)=>{
  const chunks=[];for await(const c of req)chunks.push(c);const body=Buffer.concat(chunks).toString();
  if(!verifyPlatformRequest({method:req.method,pathname:req.url,timestamp:req.headers['x-v79-timestamp'],signature:req.headers['x-v79-signature'],body,secret})){res.writeHead(401).end();return;}
  const event=JSON.parse(body);let reference=receipts.get(event.requestId);if(!reference){reference='HELP-'+crypto.randomUUID();receipts.set(event.requestId,reference);}
  res.setHeader('content-type','application/json');res.end(JSON.stringify({accepted:true,requestId:event.requestId,reference,priority:'high'}));
 });await new Promise(r=>supportServer.listen(0,'127.0.0.1',r));
 Object.assign(fixture.env,{V79_HELP_SUPPORT_ENABLED:'1',V79_HELP_SUPPORT_SHARED_SECRET:secret,V79_HELP_SUPPORT_TIQUET_URL:'http://127.0.0.1:'+supportServer.address().port});
}

const cwd=fileURLToPath(new URL('..',import.meta.url));
const portIndex=process.argv.indexOf('--port');
const port=portIndex>=0?process.argv[portIndex+1]:process.env.PORT||'3040';
const reserve=createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));
const childPort=reserve.address().port;await new Promise(r=>reserve.close(r));
const child=spawn(process.execPath,['--import','tsx','server.ts'],{cwd,env:{...process.env,...fixture.env,V79_HUB_BIND_HOST:'127.0.0.1',PORT:String(childPort),APP_URL:`http://127.0.0.1:${port}`},stdio:'inherit'});
// Test-only session entry: disposable viewer by default, or explicitly synthetic
// owner with --owner to review reports. No real credentials or records are used.
const preview=createServer((req,res)=>{
 if(req.url==='/__qa-entry'){
  res.writeHead(302,{'set-cookie':`v79_hub_session=${fixture.tokens[ownerPreview?'synthetic-owner':'viewer-a']}; Path=/; HttpOnly; SameSite=Strict`,'location':'/?view=help'});res.end();return;
 }
 if(req.url.startsWith('/__qa-frame/')){
  const width=Number(req.url.split('/').at(-1));
  if(![320,390,768,1024,1440].includes(width)){res.writeHead(404).end();return;}
  res.setHeader('content-type','text/html; charset=utf-8');res.end(`<!doctype html><html><head><title>Customer Help QA at ${width}px</title></head><body style="margin:0;background:#dde4ee;font:14px system-ui"><p style="padding:12px;margin:0">Synthetic customer · ${width}px viewport frame · development only</p><iframe title="Customer Help ${width}px" src="/?view=help" style="display:block;width:${width}px;height:1000px;border:0;background:white"></iframe></body></html>`);return;
 }
 const upstream=request({hostname:'127.0.0.1',port:childPort,path:req.url,method:req.method,headers:req.headers},response=>{
  // Only this disposable QA proxy permits same-origin viewport frames. The real
  // Hub server's anti-framing headers remain unchanged and are not tested here.
  const headers={...response.headers};delete headers['x-frame-options'];
  if(typeof headers['content-security-policy']==='string')headers['content-security-policy']=headers['content-security-policy'].replace("frame-ancestors 'none'","frame-ancestors 'self'");
  res.writeHead(response.statusCode,headers);response.pipe(res);
 });
 upstream.on('error',()=>{res.writeHead(503);res.end('Development preview is starting.');});req.pipe(upstream);
});
preview.listen(Number(port),'0.0.0.0');
const stop=()=>child.kill();process.on('SIGTERM',stop);process.on('SIGINT',stop);
child.on('exit',code=>{supportServer?.close();preview.close();fixture.cleanup();process.exit(code||0);});
