import {createPublicKey,verify} from "node:crypto";
let cached={until:0,keys:[]};
const decode=s=>JSON.parse(Buffer.from(s,"base64url").toString("utf8"));
export function inspectGoogleJwt(token,{clientId,nonce,keys,now=Date.now()}){
  if(typeof token!=="string"||token.length>12000)throw Error("Invalid token");
  const p=token.split(".");
  if(p.length!==3)throw Error("Invalid JWT");
  const h=decode(p[0]),c=decode(p[1]);
  if(h.alg!=="RS256"||typeof h.kid!=="string")throw Error("Invalid algorithm");
  const k=keys.find(k=>k.kid===h.kid&&k.kty==="RSA");
  if(!k||!verify("RSA-SHA256",Buffer.from(p[0]+"."+p[1]),createPublicKey({key:k,format:"jwk"}),Buffer.from(p[2],"base64url")))throw Error("Invalid signature");
  const n=Math.floor(now/1000);
  if(!["https://accounts.google.com","accounts.google.com"].includes(c.iss)||c.aud!==clientId||c.nonce!==nonce||c.email_verified!==true||
      !Number.isInteger(c.exp)||c.exp<=n||!Number.isInteger(c.iat)||c.iat>n+60||c.iat<n-7200||
      typeof c.sub!=="string"||!/^[0-9]{5,64}$/.test(c.sub))throw Error("Invalid identity claims");
  const email=typeof c.email==="string"?c.email.trim().toLowerCase():"";
  if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254)throw Error("Invalid email");
  const domain=email.split("@")[1];
  // An arbitrary non-Gmail email without Google's Workspace hd claim cannot authenticate.
  if(!["gmail.com","googlemail.com"].includes(domain)&&c.hd!==domain)throw Error("Untrusted domain");
  return {sub:c.sub,email};
}
export async function verifyGoogleJwt(token,{clientId,nonce}){
  if(Date.now()>cached.until||!cached.keys.length){
    const r=await fetch("https://www.googleapis.com/oauth2/v3/certs",{signal:AbortSignal.timeout(5000),redirect:"error"});
    if(!r.ok)throw Error("Google key request failed");
    const body=await r.json();
    if(!Array.isArray(body.keys)||!body.keys.length||body.keys.length>30)throw Error("Invalid Google keys");
    cached={until:Date.now()+600000,keys:body.keys};
  }
  return inspectGoogleJwt(token,{clientId,nonce,keys:cached.keys});
}
