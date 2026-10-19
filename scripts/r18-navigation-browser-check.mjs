import { chromium } from "playwright";
import assert from "node:assert/strict";

// Synthetic browser only: local static Vite build and mocked /api responses.
// NEVER connect to production, real customer accounts, email, payments or Hub servers.
const origin = "http://127.0.0.1:4178";
const owner = {
  id: "synthetic-owner", username: "owner", fullName: "Test Operator",
  role: "admin", platformOperator: true, ownerAgent: false,
  permissions: ["overview"], workspaceOwner: true, appIds: [],
};
const viewer = {
  id: "synthetic-viewer", username: "viewer", fullName: "Test Viewer",
  role: "viewer", platformOperator: false, ownerAgent: false,
  permissions: ["overview"], workspaceOwner: false, appIds: [],
};
const browser = await chromium.launch({headless: true, args:["--no-sandbox"]});
const errorList = [];
async function session(user) {
  const context = await browser.newContext({ viewport:{width:1280,height:800} });
  await context.addInitScript(() => {
    window.WebSocket = class OfflineSocket {
      constructor(){ this.readyState=1; } close(){} send(){}
      addEventListener(){} removeEventListener(){}
    };
  });
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort("blockedbyclient");
    return route.continue();
  });
  await context.route("**/api/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") {
      return route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({user,organization:{name:"Synthetic V79 Workspace"}})});
    }
    if (path === "/api/connections/status") {
      return route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({checkedAt:new Date().toISOString(),apps:{}})});
    }
    if (path === "/api/billing/summary") {
      // Complete fake response prevents a mock-only render exception.
      // Payments are disabled: no checkout, invoices or customer records.
      return route.fulfill({status:200,contentType:"application/json",
        body:JSON.stringify({
          organization:"Synthetic Workspace",planName:"Synthetic Trial",
          status:"trial",accessStatus:"trial_active",trialEndsAt:null,
          renewalDate:null,enabledApps:[],pricing:{currency:"XCD",monthly:0,annual:0},
          selfServicePaymentsEnabled:false,sandboxTestPaymentsEnabled:false,
          manualPaymentAvailable:false,supportEmail:"preview@example.invalid",
        })});
    }
    return route.fulfill({status:200,contentType:"application/json",body:
      JSON.stringify(path === "/api/ecosystem/apps" ? [] : {})});
  });
  const page = await context.newPage();
  page.on("pageerror",e=>errorList.push(String(e).slice(0,240)));
  return {context,page};
}
async function heading(page,name){ await page.getByRole("heading",{name,exact:true}).first().waitFor({timeout:15000}); }
try {
  const {context,page}=await session(owner);
  await page.goto(origin+"/");
  await page.locator(".hub-dashboard").waitFor({timeout:15000});
  const nav = page.locator('aside[aria-label="Primary workspace navigation"]');
  await nav.getByRole("button",{name:"My Apps",exact:true}).click();
  await heading(page,"Ecosystem app launcher");
  assert.equal(new URL(page.url()).searchParams.get("view"),"connections");
  await page.reload();
  await heading(page,"Ecosystem app launcher");
  console.log("REAL_BROWSER_REFRESH_MY_APPS=PASS");

  await page.goBack({waitUntil:"domcontentloaded"});
  await page.locator(".hub-dashboard").waitFor({timeout:15000});
  await page.goForward({waitUntil:"domcontentloaded"});
  await heading(page,"Ecosystem app launcher");
  console.log("REAL_BROWSER_HISTORY_BACK_FORWARD=PASS");

  await nav.getByRole("button",{name:"Billing",exact:true}).click();
  await heading(page,"Plans & billing");
  await page.reload();
  await heading(page,"Plans & billing");
  console.log("REAL_BROWSER_REFRESH_BILLING=PASS");
  await page.goto(origin+"/?view=security");
  await heading(page,"Security & access");
  console.log("REAL_BROWSER_DIRECT_SECURITY_DEEPLINK=PASS");
  await context.close();

  const limited=await session(viewer);
  await limited.page.goto(origin+"/?view=admin");
  await limited.page.locator(".hub-dashboard").waitFor({timeout:15000});
  assert.equal(new URL(limited.page.url()).searchParams.has("view"),false);
  assert.equal(await limited.page.getByRole("heading",{name:"V79 Platform Admin"}).count(),0);
  console.log("REAL_BROWSER_UNAUTHORIZED_VIEW_REJECTED=PASS");
  await limited.context.close();
  assert.deepEqual(errorList,[],"no JavaScript page errors");
  console.log("REAL_BROWSER_PAGE_ERRORS=NONE");
} finally { await browser.close(); }
