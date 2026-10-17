// Sentinel owner-pilot grant enrollment boundary.
// The route using this policy must additionally require authenticated platform
// owner membership, same-origin mutation, a live source-verified tenant mapping,
// and default-off feature switch. No grant is issued by importing this module.
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const CONFIRM="AUTHORIZE_ONE_V79_SENTINEL_PILOT";
const MAX_SECONDS=24*3600;

export function validateSentinelOwnerGrantRequest({
  body,session,user,ownerOrganizationId,expected,now=Date.now()
}={}){
  if(!Number.isFinite(now) || !body || typeof body!=="object" ||
      Array.isArray(body) ||
      Object.keys(body).sort().join("|")!=="actions|confirmation|expiresAt" ||
      body.confirmation!==CONFIRM ||
      !Array.isArray(body.actions) || body.actions.length!==1 ||
      body.actions[0]!=="ticket.create" ||
      typeof body.expiresAt!=="string" ||
      !Number.isFinite(Date.parse(body.expiresAt)) ||
      Date.parse(body.expiresAt)<=now+60_000 ||
      Date.parse(body.expiresAt)>now+MAX_SECONDS*1000 ||
      !session || session.organizationId!==ownerOrganizationId ||
      session.mfaVerified!==true ||
      !Number.isFinite(session.mfaVerifiedAt) ||
      now-session.mfaVerifiedAt<0 || now-session.mfaVerifiedAt>5*60_000 ||
      !user || user.id!==session.userId || user.mfaEnabled!==true ||
      !expected || typeof expected!=="object" ||
      ![expected.sentinelCustomerId,expected.tiquetAccountId,
        expected.tiquetClientId,ownerOrganizationId].every(x=>UUID.test(x||"")))
    throw new Error("Owner MFA verification or exact Sentinel pilot mapping missing");
  return {
    proposal:{
      serviceId:"v79-sentinel",
      sentinelCustomerId:expected.sentinelCustomerId,
      organizationId:ownerOrganizationId,
      tiquetAccountId:expected.tiquetAccountId,
      tiquetClientId:expected.tiquetClientId,
      actions:["ticket.create"],
      expiresAt:body.expiresAt
    },
    reviewer:{
      role:"owner",
      userId:session.userId,
      mfaConfirmed:true,
      mfaVerifiedAt:session.mfaVerifiedAt
    }
  };
}
export function validateSentinelOwnerRevocation({
  grantId,confirmation,session,user,ownerOrganizationId,now=Date.now()
}={}){
  if(!UUID.test(grantId||"") || confirmation!=="REVOKE_V79_SENTINEL_PILOT" ||
    !Number.isFinite(now) || !session || !user ||
    session.organizationId!==ownerOrganizationId ||
    user.id!==session.userId || user.mfaEnabled!==true ||
    session.mfaVerified!==true || !Number.isFinite(session.mfaVerifiedAt) ||
    now-session.mfaVerifiedAt<0 || now-session.mfaVerifiedAt>5*60_000)
    throw new Error("Fresh owner MFA and exact grant revocation required");
  return {
    grantId,reviewer:{role:"owner",userId:session.userId,mfaConfirmed:true,
      mfaVerifiedAt:session.mfaVerifiedAt},now
  };
}
