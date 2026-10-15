// Test-only preload, inherited by spawned Hub processes. No live destinations,
// even when a fixture forgets an internal URL override or inherits a real env.
const keys=['POS_BASE_URL','ACADEMY_INTERNAL_URL','TIQUET_INTERNAL_URL','FFPRO_INTERNAL_URL',
  'MARKETING_INTERNAL_URL','LASERTAG_INTERNAL_URL','WEBSITE_INTERNAL_URL','GAMES_INTERNAL_URL','V79_AGENT_INTERNAL_URL'];
const loopback=new Set(['127.0.0.1','localhost','[::1]','::1']);
for(const key of keys){
  let safe=false;try{safe=loopback.has(new URL(process.env[key]||'').hostname);}catch{}
  if(!safe)process.env[key]='http://127.0.0.1:9';
}
const actualFetch=globalThis.fetch;
globalThis.fetch=async(input,options)=>{
  const url=new URL(typeof input==='string'||input instanceof URL?input:input.url);
  if(!loopback.has(url.hostname))throw Error('Isolated test rejected a non-loopback network request');
  return actualFetch(input,options);
};
