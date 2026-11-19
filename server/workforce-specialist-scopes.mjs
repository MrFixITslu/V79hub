import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const bytes=readFileSync(new URL('../agent-service/workforce/integration-scopes.json',import.meta.url));
if(createHash('sha256').update(bytes).digest('hex')!=='616f9093e3ee4ac15ce0b45af92005c10df234f64a5c058fc20d5fa07211394f')throw Error('Specialist scope integrity failed');
const scopes=JSON.parse(bytes);
export const specialistSystems=id=>Object.hasOwn(scopes,id)?[...scopes[id]]:[];
export function assertSpecialistSystem(role,system){if(!specialistSystems(role).includes(system))throw Error('Specialist is not authorised for this application');}
