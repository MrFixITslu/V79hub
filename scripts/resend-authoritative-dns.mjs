import { execFileSync } from "node:child_process";

export const V79_EXPECTED_DNS = Object.freeze({
  hubA:"199.223.249.193",
  rsend:"rsend.forge.rmta.net",
  send:"send.forge.rmta.net",
});

export function parseAnswer(output,type,host){
  const wanted=host.toLowerCase().replace(/\.$/,"");
  const results=[];
  for(const line of String(output).split(/\r?\n/)){
    const v=line.trim().split(/\s+/);
    if(v.length<5)continue;
    if(v[0].toLowerCase().replace(/\.$/,"")!==wanted)continue;
    if(v[3]?.toUpperCase()!==type)continue;
    results.push(v.slice(4).join(" ").replace(/^"/,"").replace(/"$/,""));
  }
  return results;
}

export function analyzeAuthoritativeDns(answers,{nameservers=["ns1.domain.com","ns2.domain.com"]}={}){
  const issues=[];const checks={};
  const normalize=v=>String(v||"").replace(/\.$/,"").toLowerCase();
  for(const server of nameservers){
    const data=answers[server]||{};
    const a=data.hubA||[], cname=data.hubCname||[];
    const rsend=data.rsendCname||[],send=data.sendCname||[];
    const dkim=data.dkimTxt||[],dmarc=data.dmarcTxt||[];
    const siteHasA=a.includes(V79_EXPECTED_DNS.hubA);
    const siteHasCname=cname.length>0;
    const validRsend=rsend.length===1&&normalize(rsend[0])===V79_EXPECTED_DNS.rsend;
    const validSend=send.length===1&&normalize(send[0])===V79_EXPECTED_DNS.send;
    checks[server]={
      hubAValid:siteHasA,hubConflictingCname:siteHasCname,
      rsendCnameValid:validRsend,sendCnameValid:validSend,
      dkimPublished:dkim.some(v=>String(v).includes("p=")),
      dmarcPublished:dmarc.some(v=>String(v).includes("v=DMARC1")),
    };
    if(!siteHasA)issues.push(server+":hub_A_missing_or_wrong");
    if(siteHasCname)issues.push(server+":hub_CNAME_conflicts_with_application");
    if(!validRsend)issues.push(server+":rsend_CNAME_missing_or_wrong");
    if(!validSend)issues.push(server+":send_CNAME_missing_or_wrong");
    if(!checks[server].dkimPublished)issues.push(server+":DKIM_missing");
    if(!checks[server].dmarcPublished)issues.push(server+":DMARC_missing");
  }
  return {
    readyForResendVerification:issues.filter(x=>!x.includes(":hub_")).length===0,
    hubDnsSafe:issues.filter(x=>x.includes(":hub_")).length===0,
    problems:issues,checks,
    note:"Public DNS only. Resend account status is authoritative for provider verification.",
  };
}

function queryRaw(ns,host,kind) {
  try {
    return execFileSync("dig",["@"+ns,"+time=3","+tries=1","+norecurse","+noall","+answer",host,kind],
      {encoding:"utf8",timeout:4500});
  }catch {return "";}
}
const unique = a => [...new Set(a)];
export function readAuthoritativeDns(nameservers=["ns1.domain.com","ns2.domain.com"]){
  const out={};
  for(const ns of nameservers){
    // Ask for both A and CNAME; misconfigured DNS can return a CNAME in
    // response to an A lookup while hiding it on a standalone CNAME query.
    const hubAAnswer=queryRaw(ns,"hub.v79sl.com","A");
    const hubCnameAnswer=queryRaw(ns,"hub.v79sl.com","CNAME");
    const hubAnswers=hubAAnswer+"\n"+hubCnameAnswer;
    out[ns]={
      hubA:unique(parseAnswer(hubAnswers,"A","hub.v79sl.com")),
      hubCname:unique(parseAnswer(hubAnswers,"CNAME","hub.v79sl.com")),
      rsendCname:parseAnswer(queryRaw(ns,"rsend.v79sl.com","CNAME"),"CNAME","rsend.v79sl.com"),
      sendCname:parseAnswer(queryRaw(ns,"send.v79sl.com","CNAME"),"CNAME","send.v79sl.com"),
      dkimTxt:parseAnswer(queryRaw(ns,"resend._domainkey.v79sl.com","TXT"),"TXT","resend._domainkey.v79sl.com"),
      dmarcTxt:parseAnswer(queryRaw(ns,"_dmarc.v79sl.com","TXT"),"TXT","_dmarc.v79sl.com"),
    };
  }
  return out;
}
if(process.argv[1]&&import.meta.url===new URL("file://"+process.argv[1]).href){
  console.log(JSON.stringify(analyzeAuthoritativeDns(readAuthoritativeDns()),null,2));
}
