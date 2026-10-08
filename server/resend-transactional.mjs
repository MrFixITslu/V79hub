import { createHash } from "node:crypto";

const DESTINATION = "https://api.resend.com/emails";
const EMAIL_RE = /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/;
const SENDER_RE = /^(?:[^<>\r\n]+\s+<([A-Z0-9._%+-]+@v79sl\.com)>|([A-Z0-9._%+-]+@v79sl\.com))$/i;

export function validateResendSenderConfig({apiKey,from,replyTo,hubUrl}) {
  if (!String(apiKey||"").startsWith("re_") || String(apiKey||"").length<12)
    throw new Error("A nonempty scoped Resend API credential is required");
  const match=String(from||"").trim().match(SENDER_RE);
  if (!match || !EMAIL_RE.test(match[1]||match[2]))
    throw new Error("A sender on the verified v79sl.com domain is required");
  if (!EMAIL_RE.test(String(replyTo||"")) || /[\r\n]/.test(replyTo))
    throw new Error("A valid Reply-To address is required");
  let url;
  try {url=new URL(hubUrl);}
  catch {throw new Error("Valid Hub public URL is required");}
  if (url.protocol!=="https:" || url.hostname!=="hub.v79sl.com" || url.username || url.password)
    throw new Error("Hub outbound links must use its canonical HTTPS hostname");
  return Object.freeze({from:from.trim(),replyTo,hubUrl:url.origin});
}

export function createResendTransactionalSender({apiKey,from,replyTo,hubUrl,fetchImpl=fetch}) {
  const config=validateResendSenderConfig({apiKey,from,replyTo,hubUrl});
  async function deliver({to,subject,text,idempotencyKey}) {
    if(!EMAIL_RE.test(to) || /[\r\n]/.test(subject)|| !text || /[\r\n]/.test(to))
      throw new Error("Invalid email recipient or content");
    const headers={
      authorization:"Bearer "+apiKey,
      "content-type":"application/json",
    };
    if(idempotencyKey)headers["Idempotency-Key"]=idempotencyKey;
    const response=await fetchImpl(DESTINATION,{
      method:"POST", headers,
      body:JSON.stringify({from:config.from,to:[to],
        reply_to:config.replyTo,subject,text}),
      signal:AbortSignal.timeout(8000),
    });
    return response.ok===true;
  }
  return Object.freeze({
    // Staging diagnostic is not exposed through a live HTTP endpoint and has
    // no customer links, reset tokens, or claimable trial entitlement.
    async sendDiagnostic(to) {
      return deliver({
        to,
        subject:"V79 Hub — Isolated Resend Integration Check",
        text:"V79 Digital transactional sending test. This message was sent "+
          "from an isolated V79 Hub staging process using a restricted "+
          "sending-only key. No account access, subscription, or "+
          "trial status was changed. No action is required.",
        idempotencyKey:"v79-staging-resend-diagnostic-20261008",
      });
    },
    async sendInvitation({to,inviteUrl,invitationId,kind,expiresAt}) {
      if (!["owner","team"].includes(kind) || !/^[a-f0-9-]{36}$/i.test(invitationId||""))
        throw new Error("Invalid invitation");
      const url=new URL(inviteUrl);
      const prefix=kind==="owner"?"invite=":"teamInvite=";
      if (url.origin!==config.hubUrl || url.pathname!=="/" ||
          !url.hash.slice(1).startsWith(prefix) ||
          url.hash.length<prefix.length+20 ||
          !Number.isFinite(Date.parse(expiresAt))) {
        throw new Error("Invalid Hub invitation URL");
      }
      const key="v79invite-"+createHash("sha256")
        .update(String(invitationId)+":"+kind).digest("hex");
      return deliver({
        to,
        subject:kind==="owner"?"Your V79 Hub business invitation":"Your V79 Hub team invitation",
        idempotencyKey:key,
        text:"You have been invited to V79 Hub. Accept your invitation before "+
          new Date(expiresAt).toUTCString()+":\n"+inviteUrl+
          "\nIf this was unexpected, ignore the invitation. "+
          "For help contact "+config.replyTo+".",
      });
    },
    async sendPasswordReset(to,resetUrl) {
      const u=new URL(resetUrl);
      if (u.origin!==config.hubUrl || !u.searchParams.get("reset"))
        throw new Error("Password reset URL is not a canonical Hub reset link");
      return deliver({
        to,subject:"Reset your V79 Hub password",
        text:"A password reset was requested for your V79 Hub account. "+
          "Use this link within 30 minutes: "+resetUrl+
          "\n\nIf you did not request this, ignore this message. "+
          "For help contact "+config.replyTo+".",
      });
    },
    async sendTrialReminder(reminder) {
      if (!["seven_days","one_day","expired"].includes(reminder.kind))
        throw new Error("Unrecognised trial reminder stage");
      const end=new Date(reminder.trialEndsAt);
      if (!Number.isFinite(end.getTime()) || !reminder.key)
        throw new Error("Invalid reminder dates or durable claim");
      const ended=reminder.kind==="expired";
      const subject=ended?"Your V79 Hub beta trial has ended":
        reminder.kind==="one_day"?"Your V79 Hub beta trial ends tomorrow":
        "Your V79 Hub beta trial ends in seven days";
      const message=ended?"Your beta trial has ended.":
        "Your beta trial ends on "+end.toUTCString()+".";
      const key="v79trial-"+createHash("sha256").update(reminder.key).digest("hex");
      return deliver({to:reminder.email,subject,
        idempotencyKey:key,
        text:message+"\nReview subscription options: "+config.hubUrl+
          "\nFor help contact "+config.replyTo+"."});
    },
  });
}
