import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveOllamaNativeRuntime,runOllamaOwnerAssistant} from '../src/ollama-native.js';
import {createLocalExecutiveSelector} from '../src/ollama-executive.js';
test('default and explicit -1 remove the Ollama output token cap',()=>{
 for(const value of [undefined,'','-1',' -1 ','0','invalid','-2'])assert.equal(resolveOllamaNativeRuntime({...(value===undefined?{}:{OLLAMA_MAX_TOKENS:value})}).maxTokens,-1);
 assert.equal(resolveOllamaNativeRuntime({OLLAMA_MAX_TOKENS:'200'}).maxTokens,200);
});
test('native chat passes unlimited output to Ollama without changing timeout or context',async()=>{
 let body:any;
 const result=await runOllamaOwnerAssistant('Synthetic request',{env:{OLLAMA_MAX_TOKENS:'-1'},fetchImpl:async(_url,options)=>{body=JSON.parse(String(options?.body));return new Response(JSON.stringify({message:{content:'Synthetic response'}}))}});
 assert.equal(body.options.num_predict,-1);assert.equal(body.options.num_ctx,2048);assert.equal(resolveOllamaNativeRuntime({OLLAMA_MAX_TOKENS:'-1'}).timeoutMs,90000);assert.equal(result.output,'Synthetic response');
});
test('executive ranking does not reintroduce the former 120/180 token ceiling',async()=>{
 let body:any;
 const selector=createLocalExecutiveSelector({env:{OLLAMA_MAX_TOKENS:'-1'},fetchImpl:async(_url,options)=>{body=JSON.parse(String(options?.body));return new Response(JSON.stringify({message:{content:'{"findingIds":[]}'}}))}});
 await selector({stage:'coo',candidates:[]});assert.equal(body.options.num_predict,-1);assert.equal(body.format,'json');
});
