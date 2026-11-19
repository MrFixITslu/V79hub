import {createServer} from 'node:https';
import {request} from 'node:http';
import {readFileSync} from 'node:fs';
if(process.env.GITHUB_ACTIONS!=='true'||process.env.V79_EPHEMERAL_CI!=='1')throw Error('CI only');
const tls={key:readFileSync('/run/v79-stage-tls/key.pem'),cert:readFileSync('/run/v79-stage-tls/cert.pem')};
const targets=[
  {listen:3443,host:'ffpro',port:3010,canonical:'ffpro.v79sl.com',paths:new Set(['/api/gateway/webhooks/tiquet/planning/approved','/api/gateway/webhooks/tiquet/planning/closed','/api/gateway/webhooks/tiquet/paid'])},
  {listen:3444,host:'tiquet',port:3050,canonical:'tiquet.v79sl.com',paths:new Set(['/api/gateway/ffpro/planning/ready'])}
];
for(const t of targets)createServer(tls,(req,res)=>{
  if(req.method!=='POST'||!t.paths.has(req.url)){res.writeHead(404);res.end();return;}
  const upstream=request({hostname:t.host,port:t.port,path:req.url,method:'POST',headers:{...req.headers,host:t.canonical,'x-forwarded-proto':'https'}},r=>{
    res.writeHead(r.statusCode||502,r.headers);r.pipe(res);
  });
  upstream.setTimeout(12000,()=>upstream.destroy());
  upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502);res.end();});
  req.pipe(upstream);
}).listen(t.listen,'0.0.0.0');
