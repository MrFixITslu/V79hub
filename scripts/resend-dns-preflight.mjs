import {resolveNs,resolveMx,resolveTxt} from "node:dns/promises";

export function analyzeResendDns({domain,nameservers,rootTxt,dmarcTxt,returnPathTxt,returnPathMx,dkimTxt,dkimHost}) {
  const normalize = x => String(x||"").toLowerCase().replace(/\.$/,"");
  const ns = nameservers.map(normalize);
  const spf = rootTxt.filter(x=>x.startsWith("v=spf1"));
  const bounceSpf = returnPathTxt.filter(x=>x.startsWith("v=spf1"));
  const dmarc = dmarcTxt.filter(x=>x.startsWith("v=DMARC1"));
  const dkim = dkimTxt.filter(x=>x.startsWith("v=DKIM1") || x.includes("p="));
  const checks = {
    nameservers:ns,
    rootSpfRecords:spf.length,
    dmarcPresent:dmarc.length===1,
    returnPathSpfPresent:bounceSpf.length===1,
    returnPathMxPresent:returnPathMx.length>0,
    dkimHostQueried:dkimHost || null,
    dkimPresent:dkimHost ? dkim.length>0 : null,
  };
  const warnings=[];
  if(spf.length>1)warnings.push("Duplicate SPF TXT records at domain apex; consolidate before sending.");
  if(dmarc.length===0)warnings.push("No apex DMARC policy; add a monitoring policy after reviewing existing domain mail.");
  if(!checks.returnPathSpfPresent)warnings.push("No return-path SPF found; enter the exact Resend SPF host and value.");
  if(!checks.returnPathMxPresent)warnings.push("No return-path MX found; add the exact Resend MX host and target.");
  if(dkimHost && !checks.dkimPresent)warnings.push("Requested DKIM selector not found; use exact Resend dashboard record.");
  if(!dkimHost)warnings.push("DKIM selector not supplied; dashboard-specific DKIM record not checked.");
  return {domain,checks,warnings,verified:false,comment:"DNS observations only: Resend dashboard must confirm verification."};
}

async function txt(name){try{return (await resolveTxt(name)).map(parts=>parts.join(""));}catch{return [];}}
async function ns(name){try{return await resolveNs(name);}catch{return [];}}
async function mx(name){try{return await resolveMx(name);}catch{return [];}}
export async function queryResendDns({domain="v79sl.com",returnPath="send.v79sl.com",dkimHost}={}) {
  if(domain!=="v79sl.com" || !/^(?:[a-z0-9_-]+\.)*v79sl\.com$/i.test(returnPath) ||
      (dkimHost && !/^(?:[a-z0-9_-]+\.)+v79sl\.com$/i.test(dkimHost))) {
    throw new Error("Only public v79sl.com DNS hosts are accepted.");
  }
  return analyzeResendDns({
    domain,nameservers:await ns(domain),rootTxt:await txt(domain),
    dmarcTxt:await txt("_dmarc."+domain),returnPathTxt:await txt(returnPath),
    returnPathMx:await mx(returnPath),dkimTxt:dkimHost?await txt(dkimHost):[],
    dkimHost,
  });
}
if(process.argv[1] && import.meta.url===new URL("file://"+process.argv[1]).href) {
  const dkimArg=process.argv.find(a=>a.startsWith("--dkim-host="));
  const returnArg=process.argv.find(a=>a.startsWith("--return-path="));
  const dkimHost=dkimArg?.slice("--dkim-host=".length);
  const returnPath=returnArg?.slice("--return-path=".length) || "send.v79sl.com";
  try {console.log(JSON.stringify(await queryResendDns({dkimHost,returnPath}),null,2));}
  catch(err) {console.error("DNS audit blocked:",err.message);process.exitCode=2;}
}
