/**
 * Bounded audit retention that preserves the durable creation proof required
 * to safely delete an isolated Sentinel QA organization.
 *
 * Keeps up to max events, retaining all Sentinel creation markers ahead of
 * older non-marker events. It never mutates input or discloses credentials.
 */
const sentinelMarker="sentinel_qa_tenant_created";
export function retainSentinelAuditMarkers(events, max=5000) {
  if (!Array.isArray(events) || !Number.isSafeInteger(max) || max<1) {
    throw Error("Invalid audit history or retention limit");
  }
  if (events.length<=max) return events;
  const keep=new Set();
  for(let i=0;i<events.length;i++){
    if(events[i]?.type===sentinelMarker)keep.add(i);
  }
  if(keep.size>=max){
    throw Error("Sentinel QA markers exceed safe audit retention limit");
  }
  let remaining=max-keep.size;
  for(let i=events.length-1;i>=0 && remaining>0;i--){
    if(keep.has(i))continue;
    keep.add(i);
    remaining--;
  }
  return events.filter((_event,i)=>keep.has(i));
}
