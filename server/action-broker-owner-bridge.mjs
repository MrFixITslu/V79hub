/**
 * A distinct, founder-only MCP ACTION OAuth approval bridge.
 * Do not reuse Evidence Gateway grants/keys or grant actions from model output.
 */
import express from "express";
import { timingSafeEqual } from "node:crypto";

const REQUEST = /^[A-Za-z0-9_-]{43}$/;
const ISSUER = "https://actions.v79sl.com/";
const RESOURCE = ISSUER + "mcp";
const SCOPE = "hub:work_item.propose";
const escapeHtml = value => String(value).replace(/[&<>"']/g, x => ({
  "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;",
}[x]));

export function registerActionBrokerOwnerBridge(app, {
  ownerMfaContext, sameOrigin, readBridgeToken, ownerActive, ownerSubject,
  brokerBaseUrl, fetchImpl = fetch, now = Date.now,
}) {
  const url = new URL(brokerBaseUrl);
  if (url.protocol !== "http:" || url.hostname !== "v79-action-broker" ||
      url.port !== "8766" || url.pathname !== "/" || url.username ||
      url.password || url.search || url.hash) {
    throw new Error("Action OAuth broker must use its fixed private origin");
  }
  const loadedKey = () => {
    try { return readBridgeToken() || ""; } catch { return ""; }
  };
  const fresh = req => {
    const at = req.user?.mfaVerifiedAt;
    return Number.isFinite(at) && now() >= at && now()-at <= 300000;
  };
  function secure(res) {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("X-Frame-Options", "DENY");
    res.setHeader("Content-Security-Policy",
      "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
  }
  function page(res, title, contents) {
    secure(res);
    return res.type("html").send(
      '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1">'+
      '<title>'+escapeHtml(title)+'</title><style>'+
      'body{font:17px system-ui,-apple-system,sans-serif;background:#f5f7fb;color:#1b283a;margin:0;padding:24px}'+
      'main{max-width:660px;margin:9vh auto;padding:36px;border:1px solid #e0e6ed;border-radius:20px;background:white}'+
      'h1{font-size:clamp(27px,5vw,36px);letter-spacing:-.03em}p{line-height:1.6}'+
      'button{padding:14px 20px;font:inherit;border:1px solid #087c89;border-radius:10px;background:#087c89;color:white;margin:6px}'+
      'button.secondary{background:white;color:#17212e;border-color:#c6ced6}small{overflow-wrap:anywhere}'+
      '</style><main>'+contents+'</main>'
    );
  }
  async function broker(path, body) {
    const key = loadedKey();
    if (key.length < 32) throw new Error("Action broker bridge not configured");
    const response = await fetchImpl(new URL(path,url),{
      method:body===undefined ? "GET":"POST",
      headers:{"x-v79-action-internal":key,"content-type":"application/json"},
      ...(body===undefined?{}:{body:JSON.stringify(body)}),
      redirect:"error", signal:AbortSignal.timeout(7000),
    });
    const text = await response.text();
    if (!response.ok || Buffer.byteLength(text)>8192) throw new Error("Broker denied request");
    return JSON.parse(text);
  }
  // Machine-only, exact-key owner status. Never accept a browser cookie or token.
  app.get("/internal/action-broker/owner-active",(req,res)=>{
    secure(res);
    const expected=loadedKey(),given=String(req.get("x-v79-action-internal")||"");
    if (req.get("origin")||req.get("cookie")||req.get("authorization")||
        expected.length<32||Buffer.byteLength(given)!==Buffer.byteLength(expected)||
        !timingSafeEqual(Buffer.from(given),Buffer.from(expected))) {
      return res.status(403).json({active:false});
    }
    return res.json({active:ownerActive()===true});
  });

  app.get("/api/agent/action-broker/authorize", async(req,res)=>{
    if (!ownerMfaContext(req)) return res.status(403).json({error:"MFA-verified Hub founder required"});
    const id=String(req.query.request||"");
    if (!REQUEST.test(id)) return res.status(400).json({error:"Invalid action consent request"});
    try {
      const info=await broker("/internal/request?request="+encodeURIComponent(id));
      if (info.requestId!==id||info.resource!==RESOURCE||info.scope!==SCOPE||
          !/^[a-f0-9]{64}$/.test(info.clientIdHash)) throw new Error("Action consent mismatch");
      const summary='<h1>Connect V79 Action Broker</h1>'+
        '<p>This MCP connection can <strong>propose an internal Hub work item only</strong>. '+
        'It cannot approve or execute its own proposal, email customers, change permissions, post marketing content, '+
        'bill anyone or deploy software. Every proposed task still requires your explicit approval in Hub.</p>'+
        '<p><strong>Permission:</strong> '+escapeHtml(SCOPE)+
        '<br><strong>OAuth resource:</strong> '+escapeHtml(RESOURCE)+
        '<br><strong>Client fingerprint:</strong> '+escapeHtml(info.clientIdHash)+
        '</p><p>Access tokens expire after 5 minutes; action grants expire after 1 hour and are revocable.</p>';
      if (!fresh(req)) {
        return page(res,"Owner MFA required",summary+
          '<p><strong>Complete a fresh owner MFA step-up in Hub and restart this connection.</strong></p>');
      }
      return page(res,"Approve V79 Action Broker",summary+
        '<form method="post" action="/api/agent/action-broker/authorize">'+
        '<input type="hidden" name="requestId" value="'+escapeHtml(id)+'">'+
        '<button name="approved" value="true">Allow task proposals</button>'+
        '<button name="approved" class="secondary" value="false">Deny</button></form>');
    } catch {
      return res.status(503).json({error:"Action consent unavailable or expired"});
    }
  });

  app.post("/api/agent/action-broker/authorize",
    express.urlencoded({extended:false,limit:"2kb"}),async(req,res)=>{
      if (!ownerMfaContext(req)||!fresh(req)||!sameOrigin(req)) {
        return res.status(403).json({error:"Fresh owner MFA and same-origin action consent required"});
      }
      if (!req.body || Object.keys(req.body).sort().join(",")!=="approved,requestId" ||
          !REQUEST.test(req.body.requestId) || !["true","false"].includes(req.body.approved)) {
        return res.status(400).json({error:"Invalid action consent"});
      }
      try {
        const data=await broker("/internal/consent",{
          requestId:req.body.requestId,subject:ownerSubject(),approved:req.body.approved==="true",
        });
        const callback=new URL(data.redirect);
        if (callback.protocol!=="https:"||callback.host!=="chatgpt.com"||
            !(callback.pathname==="/connector_platform_oauth_redirect"||
              /^\/connector\/oauth\/[A-Za-z0-9_-]{8,160}$/.test(callback.pathname))||
            callback.hash) throw new Error("Action callback denied");
        secure(res);
        return res.redirect(303,callback.href);
      } catch {
        return page(res.status(409),"Restart action connection",
          "<h1>Action consent not completed</h1><p>This request expired, changed or was denied. " +
          "Restart the connection and approve again. No action permission has been confirmed.</p>");
      }
    });

  app.get("/api/agent/action-broker/access",(req,res)=>{
    if (!ownerMfaContext(req)) return res.status(403).json({error:"Owner MFA required"});
    return page(res,"V79 Action Broker",
      "<h1>V79 Action Broker</h1><p>Owner-only MCP task proposals.</p>"+
      "<p>Endpoint: <strong>"+escapeHtml(RESOURCE)+"</strong></p>"+
      "<p>Proposals do not execute until a separate Hub approval.</p>"+
      '<form method="post" action="/api/agent/action-broker/revoke">'+
      '<button name="confirmation" value="REVOKE_ACTION_BROKER">Revoke all action grants</button></form>'+
      "<p>Revocation requires fresh owner MFA.</p>");
  });

  app.post("/api/agent/action-broker/revoke",
    express.urlencoded({extended:false,limit:"2kb"}),async(req,res)=>{
      if (!ownerMfaContext(req)||!fresh(req)||!sameOrigin(req)) {
        return res.status(403).json({error:"Fresh owner MFA required"});
      }
      if (!req.body||Object.keys(req.body).join(",")!=="confirmation"||
          req.body.confirmation!=="REVOKE_ACTION_BROKER") {
        return res.status(400).json({error:"Exact revocation confirmation required"});
      }
      try {
        const receipt=await broker("/internal/revoke",{subject:ownerSubject()});
        if (receipt.revoked!==true) throw new Error("No revocation receipt");
        return page(res,"Action access revoked",
          "<h1>Action access revoked</h1><p>All Action Broker access and refresh tokens have been revoked.</p>");
      } catch {
        return res.status(503).json({error:"Revocation was not verified. Disable the broker if urgent."});
      }
    });
}
