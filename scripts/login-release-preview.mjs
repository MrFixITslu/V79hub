import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const origin = "http://127.0.0.1:4179";
const output = resolve("login-release-artifacts");
await mkdir(output, { recursive: true });
const report = { screens: [], pageErrors: [], blockedExternal: [], verified: [] };
const user = { id:"synthetic", username:"synthetic-user", fullName:"Synthetic Preview Operator", role:"user", platformOperator:false, permissions:[], appIds:[] };
const contexts = [];
let browser;
try {
  browser = await chromium.launch({ headless:true, args:["--no-sandbox"] });
  async function open(size, label, reset=false) {
    const ctx = await browser.newContext({ viewport:size, reducedMotion:"reduce", deviceScaleFactor:1 });
    contexts.push(ctx);
    await ctx.route("**/*",route=>{
      const u=new URL(route.request().url());
      if(u.origin !== origin) { report.blockedExternal.push(u.origin); return route.abort("blockedbyclient"); }
      return route.continue();
    });
    await ctx.route("**/api/**",async route=>{
      const req=route.request(), p=new URL(req.url()).pathname;
      let status=200, data={};
      if(p==="/api/auth/me") {status=401;data={error:"Not signed in"};}
      else if(p==="/api/auth/recovery-status") data={emailRecoveryEnabled:true,supportEmail:"preview@example.invalid"};
      else if(p==="/api/auth/password-reset/request") data={message:"Recovery email requested (synthetic)"};
      else if(p==="/api/auth/password-reset/complete") data={message:"Password updated"};
      else if(p==="/api/auth/login") {
        const payload=JSON.parse(req.postData()||"{}");
        if(!payload.organizationId){status=409;data={organizations:[{id:"org-a",name:"Synthetic Business Workspace",slug:"demo"}]};}
        else {status=202;data={mfaRequired:true,challengeId:"synthetic-challenge"};}
      } else if(p==="/api/auth/mfa/complete-login") data={user};
      else if(p==="/api/ecosystem/apps") data=[];
      else if(p==="/api/dashboard/summary") data={generatedAt:"2026-10-15T16:00:00-04:00",apps:{}};
      await route.fulfill({status,contentType:"application/json",body:JSON.stringify(data)});
    });
    const page=await ctx.newPage();
    page.on("pageerror",e=>report.pageErrors.push({label,error:String(e)}));
    await page.goto(origin+(reset?"/?reset=synthetic-reset-token":"/"),{waitUntil:"domcontentloaded"});
    return page;
  }
  async function screenshot(page,label) {
    await page.waitForTimeout(350);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth);
    assert.ok(overflow <= 2, label+" has horizontal viewport overflow "+overflow);
    await page.screenshot({path:resolve(output,label+".png"),fullPage:true,animations:"disabled"});
    report.screens.push({label,size:page.viewportSize(),overflow});
    console.log("CAPTURE_PASS "+label);
  }
  const desktop=await open({width:1440,height:810},"desktop");
  await desktop.getByRole("heading",{name:"Sign in to your account"}).waitFor();
  await screenshot(desktop,"login-1440x810");
  assert.equal(await desktop.getByRole("button",{name:/Continue with Google/}).isDisabled(),true,"Google OAuth unavailable must be clearly disabled");
  report.verified.push("Google sign-in disabled without configured OAuth");

  await desktop.getByRole("button",{name:"Forgot password?"}).click();
  await desktop.getByRole("heading",{name:"Reset your password"}).waitFor();
  await desktop.locator('input[type="email"]').fill("synthetic@example.invalid");
  await desktop.getByRole("button",{name:"Send reset instructions"}).click();
  await desktop.getByText("Recovery email requested (synthetic)").waitFor();
  await screenshot(desktop,"login-recovery-desktop");
  await desktop.getByRole("button",{name:"Back to sign in"}).click();
  await desktop.getByRole("heading",{name:"Sign in to your account"}).waitFor();
  report.verified.push("recovery request and return to sign-in");

  await desktop.locator('input[autocomplete="username"]').fill("synthetic@example.invalid");
  await desktop.locator('input[autocomplete="current-password"]').fill("synthetic-password-only");
  await desktop.getByRole("button",{name:"Sign in",exact:true}).click();
  await desktop.getByText("Choose the business workspace you want to open.").waitFor();
  await desktop.locator("select").selectOption("org-a");
  await desktop.getByRole("button",{name:"Sign in",exact:true}).click();
  await desktop.getByRole("heading",{name:"Two-factor authentication"}).waitFor();
  await screenshot(desktop,"login-mfa-synthetic");
  await desktop.locator('input[autocomplete="one-time-code"]').fill("123456");
  await desktop.getByRole("button",{name:"Verify and continue"}).click();
  await desktop.getByText(/Welcome back, Synthetic Preview Operator/).waitFor();
  report.verified.push("workspace picker, synthetic MFA challenge and callback");

  const reset=await open({width:1440,height:810},"reset",true);
  await reset.getByRole("heading",{name:"Choose a new password"}).waitFor();
  await reset.locator('input[autocomplete="new-password"]').first().fill("synthetic-password-12");
  await reset.locator('input[autocomplete="new-password"]').last().fill("synthetic-password-12");
  await reset.getByRole("button",{name:"Update password"}).click();
  await reset.getByText("Password updated. Sign in with your new password.").waitFor();
  report.verified.push("password reset completion (synthetic)");

  for(const [size,label] of [[{width:390,height:844},"login-mobile-390"],[{width:768,height:1024},"login-tablet-768"],[{width:1440,height:900},"login-desktop-1440x900"]]) {
    const page=await open(size,label);
    await page.getByRole("heading",{name:"Sign in to your account"}).waitFor();
    await screenshot(page,label);
  }
} finally {
  for (const ctx of contexts) await ctx.close().catch(()=>{});
  await browser?.close().catch(()=>{});
}
await writeFile(resolve(output,"browser-report.json"),JSON.stringify(report,null,2));
const gallery='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V79 Hub — Login-only Release Preview</title><style>body{background:#07101c;color:#f5f8ff;font:16px system-ui;padding:24px;line-height:1.5}a{color:#65c9ff}img{display:block;width:100%;max-width:1000px;border:1px solid #3b5470;margin:12px 0 30px}h1{font-size:26px}</style><h1>V79 Hub · Login-only release preview</h1><p>Isolated browser / synthetic accounts / no connection to production.</p>'+report.screens.map(s=>'<h2>'+s.label+'</h2><a href="'+s.label+'.png"><img src="'+s.label+'.png" alt="'+s.label+'"></a>').join('');
await writeFile(resolve(output,"index.html"),gallery);
console.log("LOGIN_PREVIEW_PASS screens="+report.screens.length+" page_errors="+report.pageErrors.length);
if(report.pageErrors.length)process.exitCode=1;
