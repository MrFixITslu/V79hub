/**
 * V79 A04: offline audit of installed host's 08:00 and 19:00
 * America/St_Lucia briefing calendar. Does not schedule, run or send reports.
 * Saint Lucia operates on UTC-04:00 year-round (no daylight saving shift).
 */
const ISO_UTC=/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const DAY=/^\d{4}-\d{2}-\d{2}$/;
const SLOTS=[['morning','12:00:00'],['evening','23:00:00']];
const safeTime=(v)=>typeof v==='string'&&ISO_UTC.test(v)&&Number.isFinite(Date.parse(v))?Date.parse(v):NaN;
const trusted=(fn,value)=>{if(typeof fn!=='function')return false;try{return fn(value)===true}catch{return false}};
const asDay=(t)=>new Date(t).toISOString().slice(0,10);

/**
 * verifyReport must validate trusted file provenance + protected report content.
 * verifyInventory must certify complete listing for the bounded interval,
 * not merely that at least one report was returned. Missing inventory never
 * permits a positive "sustained" conclusion.
 */
export function auditBriefingReliability({
  reports, firstDay, days=3, asOfUtc, verifyReport, verifyInventory,
}={}) {
  const unavailable=(reason)=>Object.freeze({mode:'read-only',status:'unavailable',
    reason,slots:[],summary:{verified:0,missing:0,unverified:0,pending:0,incomplete:0}});
  const now=safeTime(asOfUtc);
  const initial=typeof firstDay==='string'&&DAY.test(firstDay) ? Date.parse(firstDay+'T00:00:00Z') : NaN;
  if (!Array.isArray(reports)||reports.length>100||!Number.isFinite(initial)||
      asDay(initial)!==firstDay||
      !Number.isSafeInteger(days)||days<1||days>14||!Number.isFinite(now))
    return unavailable('INVALID_AUDIT_SCOPE');
  const complete=trusted(verifyInventory,{firstDay,days,reports});
  const bySlot=new Map(),duplicates=new Set();
  for(const r of reports){
    if(!r || typeof r.slot!=='string'|| !/^\d{4}-\d{2}-\d{2}-(morning|evening)$/.test(r.slot))
      continue;
    if(bySlot.has(r.slot)) duplicates.add(r.slot);
    else bySlot.set(r.slot,r);
  }
  const slots=[],counts={verified:0,missing:0,unverified:0,pending:0,incomplete:0};
  const start=Date.parse(firstDay+'T00:00:00Z');
  for(let d=0;d<days;d++){
    const day=asDay(start+d*86400000);
    for (const [name,utcHour] of SLOTS){
      const slot=day+'-'+name;
      const expected=Date.parse(day+'T'+utcHour+'Z');
      const due=now>=expected+30*60_000;
      const r=bySlot.get(slot);
      let state;
      if (!due) state='pending';
      else if(duplicates.has(slot)) state='unverified';
      else if(!r) state=complete?'missing':'unverified';
      else {
        const checked=safeTime(r.checkedAt);
        // The installed Python host emits uppercase AVAILABLE/INCOMPLETE.
        // Normalize only exact known labels, matching the owner Hub reader.
        // Signature/inventory checks below still independently attest source.
        const coverage=typeof r.report?.coverage==='string'
          ? r.report.coverage.toLowerCase():null;
        if(!trusted(verifyReport,r) || r.state!=='recorded' ||
            r.report?.noActionsExecuted!==true ||
            !['available','incomplete'].includes(coverage) ||
            !Number.isFinite(checked) || checked<expected-5*60_000||
            checked>expected+30*60_000 || checked>now+60_000)
          state='unverified';
        else state=coverage==='available'?'verified':'incomplete';
      }
      counts[state]++; 
      slots.push(Object.freeze({slot,expectedAt:new Date(expected).toISOString(),state}));
    }
  }
  // This only designates an operator review candidate, not authorizes GO.
  const eligible=complete&&slots.length>=6&&counts.pending===0&&
    counts.verified===slots.length&&counts.missing===0&&counts.unverified===0;
  return Object.freeze({
    mode:'read-only',
    status:eligible?'candidate_for_owner_acceptance':'not_yet_accepted',
    inventoryVerified:complete,
    summary:Object.freeze(counts),slots:Object.freeze(slots),
  });
}
