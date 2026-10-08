import { execFileSync } from "node:child_process";
import { timingSafeEqual } from "node:crypto";

export function validateV79ReleaseConfig(environments, networks) {
  const issues=[];
  const names=["v79-hub","v79-pos","fire-finance-app","v79-tiquet-manager","v79marketing-app"];
  const hub=environments["v79-hub"]||{};
  for(const name of names) {
    if(!environments[name]) {issues.push(name+":container_missing");continue;}
    if(!networks[name]?.includes("proxy_network"))
      issues.push(name+":proxy_network_missing");
  }
  const configured=[
    ["v79-pos","V79_PLATFORM_SHARED_SECRET","V79_POS_PLATFORM_SHARED_SECRET"],
    ["fire-finance-app","V79_FFPRO_LAUNCH_SECRET","V79_FFPRO_LAUNCH_SECRET"],
    ["v79-tiquet-manager","V79_TIQUET_LAUNCH_SECRET","V79_TIQUET_LAUNCH_SECRET"],
    ["v79marketing-app","V79_MARKETING_LAUNCH_SECRET","V79_MARKETING_LAUNCH_SECRET"],
  ];
  for(const [name,serviceKey,hubKey] of configured) {
    const local=environments[name]||{};
    const expected=String(hub[hubKey] || hub[serviceKey] || "");
    const actual=String(local[name==="v79-pos"?
      (local.V79_POS_PLATFORM_SHARED_SECRET?"V79_POS_PLATFORM_SHARED_SECRET":serviceKey):
      serviceKey]||"");
    const match=actual.length>=32 && expected.length>=32 &&
      Buffer.byteLength(actual)===Buffer.byteLength(expected) &&
      timingSafeEqual(Buffer.from(actual),Buffer.from(expected));
    if(!match)issues.push(name+":signature_secret_mismatch");
  }
  if(!hub.RESEND_API_KEY || !hub.V79_HUB_EMAIL_FROM)
    issues.push("v79-hub:trial_email_provider_unconfigured");
  for(const name of names.slice(1)) {
    const local=environments[name]||{};
    const url=local.V79_HUB_INTERNAL_URL || local.HUB_INTERNAL_URL || "";
    try {
      const parsed=new URL(url);
      if(parsed.hostname!=="v79-hub" || parsed.port!=="3040" ||
        !["http:","https:"].includes(parsed.protocol))issues.push(name+":hub_route_incorrect");
    } catch {issues.push(name+":hub_route_incorrect");}
  }
  return {ready:issues.length===0,issueCount:issues.length,issues};
}

function run() {
  const names=["v79-hub","v79-pos","fire-finance-app","v79-tiquet-manager","v79marketing-app"];
  const environments={};const networks={};
  for(const name of names) {
    try {
      const raw=execFileSync("docker",["inspect",name],{encoding:"utf8",timeout:12000});
      const config=JSON.parse(raw)[0];
      environments[name]=Object.fromEntries(
        config.Config.Env.filter(x=>x.includes("=")).map(x=>[x.slice(0,x.indexOf("=")),x.slice(x.indexOf("=")+1)]));
      networks[name]=Object.keys(config.NetworkSettings.Networks||{});
    } catch {
      environments[name]=null;networks[name]=[];
    }
  }
  const result=validateV79ReleaseConfig(environments,networks);
  // The result includes only names and boolean-derived statuses, never values.
  process.stdout.write(JSON.stringify(result,null,2)+"\n");
  if(!result.ready)process.exitCode=1;
}
if(process.argv[1] && import.meta.url===new URL("file://"+process.argv[1]).href)run();
