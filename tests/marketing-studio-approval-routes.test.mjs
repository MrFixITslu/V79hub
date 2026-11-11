import test from 'node:test';
import assert from 'node:assert/strict';
import {marketingStudioApprovalRouter,validStudioApprovalBody} from '../server/marketing-studio-approval-routes.mjs';
const input={creatorUserId:'synthetic-owner',campaignId:'campaign-synthetic',packageId:'1dc5485b-40f7-46ad-a7b8-7b98556e7d0d',
 exactDigest:'a'.repeat(64),confirmExactPublication:true};
test('Studio Hub publishing body cannot smuggle actor IDs, tokens or remove explicit consent',()=>{
 assert.equal(validStudioApprovalBody(input),true);
 assert.equal(validStudioApprovalBody({...input,actorHubUserId:'forged'}),false);
 assert.equal(validStudioApprovalBody({...input,confirmExactPublication:false}),false);
 assert.equal(validStudioApprovalBody({...input,exactDigest:'wrong'}),false);
 assert.equal(validStudioApprovalBody({...input,packageId:'another-user'}),false);
});
test('Studio approval router creation does not forward or authorise anything implicitly',()=>{
 let calls=0;
 const router=marketingStudioApprovalRouter({
  approverContext:()=>null,sameOrigin:()=>true,enabled:()=>false,
  forward:async()=>{calls++;return {status:201,body:{}};}
 });
 assert.equal(typeof router,'function');
 assert.equal(calls,0);
});
