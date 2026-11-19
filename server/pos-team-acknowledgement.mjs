// A POS-assigned technician remains restricted to that role during Hub staff launches.
// Normal Hub-to-POS role mappings and tenant/user/location identity checks stay strict.
const roles = Object.freeze({manager:'MANAGER',staff:'CASHIER',viewer:'AUDITOR'});
export function validatePosTeamAcknowledgement(payload, {organizationId,userId,hubRole} = {}) {
  if (!payload || typeof payload!=='object' || Array.isArray(payload)) return null;
  if (!Object.hasOwn(roles,hubRole) || typeof organizationId!=='string' || !organizationId ||
      typeof userId!=='string' || !userId) return null;
  const expectedRole=roles[hubRole];
  const preservedTechnician=hubRole==='staff' && payload.roleKey==='TECHNICIAN';
  if (payload.provisioned!==true || payload.organizationId!==organizationId || payload.userId!==userId ||
      (payload.roleKey!==expectedRole && !preservedTechnician) ||
      !Array.isArray(payload.locationIds) || payload.locationIds.length!==1 ||
      typeof payload.locationIds[0]!=='string' || !payload.locationIds[0].trim()) return null;
  return {roleKey:payload.roleKey,locationId:payload.locationIds[0]};
}
