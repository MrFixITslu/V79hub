// Disposable cross-repository integration process. Never imports Tiquet's live DB.
import express from 'express';
import pg from 'pg';
import {pathToFileURL} from 'node:url';
const {createHubHelpRouter,HUB_HELP_PATH}=await import(pathToFileURL(process.env.V79_HELP_TIQUET_TEST_SOURCE+'/server/hubHelpSupport.js'));
const pool=new pg.Pool({host:process.env.PGHOST,port:Number(process.env.PGPORT),user:process.env.PGUSER,database:'postgres',max:6,connectionTimeoutMillis:2000});
const db={transaction(fn){return async()=>{
 const client=await pool.connect();try{await client.query('BEGIN');const tx={query:(sql,params=[])=>{let n=0;return client.query(sql.replace(/\?/g,()=>'$'+(++n)),params);}};const out=await fn(tx);await client.query('COMMIT');return out;}catch(e){await client.query('ROLLBACK');throw e;}finally{client.release();}
};}};
const app=express();app.use(express.json({limit:'32kb',verify:(req,_res,body)=>req.rawBody=Buffer.from(body)}));
app.use(HUB_HELP_PATH,createHubHelpRouter({db,config:JSON.parse(process.env.V79_HELP_TEST_CONFIG)}));
const server=app.listen(0,'127.0.0.1',()=>process.send({port:server.address().port}));
process.on('SIGTERM',()=>{server.closeAllConnections();server.close(async()=>{await pool.end();process.exit(0);});});
