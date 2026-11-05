import test from 'node:test';import assert from 'node:assert/strict';
import {specialistSystems,assertSpecialistSystem} from '../server/workforce-specialist-scopes.mjs';
test('specialist application boundaries reject unrelated tasks and unknown roles',()=>{
 assertSpecialistSystem('sales','website');assertSpecialistSystem('finance','ffpro');assertSpecialistSystem('coo','hub');
 for(const [role,system] of [['sales','ffpro'],['finance','website'],['customer-service','marketing'],['shell','hub']])assert.throws(()=>assertSpecialistSystem(role,system),/not authorised/);
 const a=specialistSystems('sales');a.push('ffpro');assert.deepEqual(specialistSystems('sales'),['website']);
});
