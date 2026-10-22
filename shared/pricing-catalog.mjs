export const PRICING_REVISION='v79-xcd-20261022-v1';
const packages=[
 {id:'starter',name:'Starter',monthlyXcd:149,appAllowance:1,staffIncluded:3},
 {id:'business',name:'Business',monthlyXcd:299,appAllowance:2,staffIncluded:5},
 {id:'business-plus',name:'Business Plus',monthlyXcd:499,appAllowance:3,staffIncluded:10},
];
const apps=[
 {id:'app-tiquet',name:'V79 Tiquet',description:'Customer requests and support tickets',supplementMonthlyXcd:0,releaseStatus:'accepted'},
 {id:'app-pos',name:'V79 POS',description:'Sales and retail operations',supplementMonthlyXcd:100,releaseStatus:'requires-release-review'},
 {id:'app-ffpro',name:'Fire Finance Pro',description:'Business income and expenses',supplementMonthlyXcd:0,releaseStatus:'requires-release-review'},
 {id:'app-marketing',name:'V79 Marketing',description:'Marketing activity',supplementMonthlyXcd:0,releaseStatus:'requires-release-review'},
];
export function pricingCatalog(){return structuredClone({revision:PRICING_REVISION,currency:'XCD',usdDivisor:2.7,annualMonthsCharged:10,extraAppMonthlyXcd:99,extraStaffMonthlyXcd:25,guidedSetupXcd:199,maxExtraStaff:100,packages,apps,mode:'owner-reviewed-request',automaticActivation:false})}
export function priceSelection(input){
 const fail=()=>{throw new Error('Choose a valid package, apps, billing period and whole number of extra staff accounts (0–100).')};
 if(!input||typeof input!=='object'||Array.isArray(input)||Object.keys(input).sort().join('|')!=='appIds|billingCycle|extraStaff|guidedSetup|packageId|revision')fail();
 if(input.revision!==PRICING_REVISION)throw new Error('Pricing changed. Refresh the catalogue before reviewing your selection.');
 const pack=packages.find(p=>p.id===input.packageId);
 if(!pack||!['monthly','annual'].includes(input.billingCycle)||typeof input.guidedSetup!=='boolean'||!Number.isSafeInteger(input.extraStaff)||input.extraStaff<0||input.extraStaff>100||!Array.isArray(input.appIds)||input.appIds.length<1||input.appIds.length>apps.length||new Set(input.appIds).size!==input.appIds.length||input.appIds.some(id=>!apps.some(app=>app.id===id)))fail();
 const chosen=apps.filter(a=>input.appIds.includes(a.id));
 const selection={revision:PRICING_REVISION,packageId:pack.id,appIds:chosen.map(a=>a.id),billingCycle:input.billingCycle,extraStaff:input.extraStaff,guidedSetup:input.guidedSetup};
 const factor=input.billingCycle==='annual'?10:1;
 const additionalApps=Math.max(0,chosen.length-pack.appAllowance);
 const lineItems=[{id:'package',label:pack.name+' package',amountXcd:pack.monthlyXcd*factor}];
 if(additionalApps)lineItems.push({id:'additional-apps',label:additionalApps+' additional app'+(additionalApps===1?'':'s'),amountXcd:additionalApps*99*factor});
 for(const app of chosen)if(app.supplementMonthlyXcd)lineItems.push({id:app.id+'-supplement',label:app.name+' supplement',amountXcd:app.supplementMonthlyXcd*factor});
 if(input.extraStaff)lineItems.push({id:'extra-staff',label:input.extraStaff+' additional staff account'+(input.extraStaff===1?'':'s'),amountXcd:input.extraStaff*25*factor});
 const recurringXcd=lineItems.reduce((n,l)=>n+l.amountXcd,0);
 return {selection,packageName:pack.name,appNames:chosen.map(a=>a.name),currency:'XCD',billingCycle:input.billingCycle,lineItems,recurringXcd,setupXcd:input.guidedSetup?199:0,totalFirstInvoiceXcd:recurringXcd+(input.guidedSetup?199:0),staffIncluded:pack.staffIncluded,extraStaff:input.extraStaff,totalStaff:pack.staffIncluded+input.extraStaff,annualSavingsXcd:input.billingCycle==='annual'?recurringXcd/5:0,requiresReleaseReview:chosen.filter(a=>a.releaseStatus!=='accepted').map(a=>a.id),activation:'requires-owner-review-and-payment-verification',charged:false};
}
export function displayPrice(amountXcd,currency='XCD'){
 if(!Number.isFinite(amountXcd)||amountXcd<0||!['XCD','USD'].includes(currency))throw new Error('Invalid display amount');
 return (currency==='USD'?'US$':'EC$')+(amountXcd/(currency==='USD'?2.7:1)).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
}
