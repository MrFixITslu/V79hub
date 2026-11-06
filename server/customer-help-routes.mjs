import {Router} from 'express';
import {createHelpService,helpCatalog,findArticle,validateQuestion} from './customer-help.mjs';
import {FEEDBACK_REASONS,validateFeedback,reportFilters,HelpFeedbackError} from './customer-help-feedback.mjs';

/** @param {{context?: (req: import('express').Request) => ({userId:string,organizationId:string}|null), sameOrigin?: (req: import('express').Request) => boolean, service?: ReturnType<typeof createHelpService>, clock?: () => number, maxPerMinute?: number, feedbackStore?: ReturnType<import('./customer-help-feedback.mjs').createHelpFeedback>|null, reportAccess?: (req: import('express').Request) => ({workspace:boolean,all:boolean})}} options */
export function customerHelpRouter({context=undefined,sameOrigin=undefined,service=createHelpService(),clock=Date.now,maxPerMinute=12,feedbackStore=null,reportAccess=(_req)=>({workspace:false,all:false})}={}) {
  const router=Router();
  // No question/history/answer persistence. These are expiring rate counters only.
  const budgets=new Map();
  let active=0;
  const feedbackBudgets=new Map();let feedbackActive=0,reportActive=0;
  router.use((req,res,next)=>{
    res.setHeader('Cache-Control','no-store');
    const actor=context?.(req);
    if(!actor?.userId||!actor?.organizationId) return res.status(401).json({error:'Sign in to Hub to use app help.'});
    res.locals.helpActor=actor;next();
  });
  router.get('/catalog',(req,res)=>res.json({...helpCatalog(),...(feedbackStore?.enabled?{feedback:{enabled:true,reasons:FEEDBACK_REASONS,...reportAccess(req)}}:{})}));
  router.get('/articles/:id',(req,res)=>{
    const article=findArticle(req.params.id);
    return article?res.json({article}):res.status(404).json({error:'This help article is unavailable.'});
  });
  router.get('/feedback/report',async(req,res)=>{
    try{
      const filters=reportFilters(req.query),access=reportAccess(req);
      if(!access.workspace||filters.scope==='all'&&!access.all)return res.status(403).json({error:'Owner permission is required for this feedback report.'});
      if(!feedbackStore?.enabled)return res.status(503).json({error:'Feedback reporting is unavailable.'});
      if(reportActive>=4){res.setHeader('Retry-After','3');return res.status(429).json({error:'Reports are busy. Please try again shortly.'});}
      reportActive++;try{return res.json(await feedbackStore.report(res.locals.helpActor,filters));}finally{reportActive--;}
    }catch(e){return res.status(e instanceof HelpFeedbackError&&e.code==='INVALID'?400:503).json({error:e instanceof HelpFeedbackError?e.message:'Feedback reporting is unavailable. Try again later.'});}
  });
  router.post('/feedback',async(req,res)=>{
    if(!sameOrigin?.(req))return res.status(403).json({error:'Open feedback in your Hub window and try again.'});
    if(Buffer.byteLength(JSON.stringify(req.body??null),'utf8')>4000)return res.status(413).json({error:'Feedback is too large.'});
    const invalid=validateFeedback(req.body);if(invalid)return res.status(400).json({error:invalid});
    if(!feedbackStore?.enabled)return res.status(503).json({error:'Feedback is unavailable. The help guide still works.'});
    const now=clock();for(const [key,budget] of feedbackBudgets)if(budget.until<=now)feedbackBudgets.delete(key);
    const {organizationId,userId}=res.locals.helpActor,key=JSON.stringify([organizationId,userId]);
    let budget=feedbackBudgets.get(key);
    if(!budget){if(feedbackBudgets.size>=5000)return res.status(503).json({error:'Feedback is busy. Try again later.'});budget={until:now+60000,count:0};feedbackBudgets.set(key,budget);}
    if(budget.count>=20||feedbackActive>=8){res.setHeader('Retry-After','60');return res.status(429).json({error:'Please wait before sending more feedback.'});}
    budget.count++;feedbackActive++;
    try{return res.json(await feedbackStore.vote(req.body,res.locals.helpActor));}
    catch(e){const code=e instanceof HelpFeedbackError?({INVALID:400,FORBIDDEN:403,EXPIRED:410}[e.code]||503):503;return res.status(code).json({error:e instanceof HelpFeedbackError?e.message:'Feedback could not be saved. Please try again.'});}
    finally{feedbackActive--;}
  });
  router.post('/chat',async(req,res)=>{
    if(!sameOrigin?.(req))return res.status(403).json({error:'Open help in your Hub window and try again.'});
    if(Buffer.byteLength(JSON.stringify(req.body??null),'utf8')>12000)return res.status(413).json({error:'This question is too long. Shorten it and try again.'});
    const invalid=validateQuestion(req.body);
    if(invalid)return res.status(400).json({error:invalid});
    const now=clock();
    for(const [key,budget] of budgets)if(budget.until<=now&&budget.active===0)budgets.delete(key);
    const {organizationId,userId}=res.locals.helpActor;
    const key=JSON.stringify([organizationId,userId]);
    let budget=budgets.get(key);
    if(budget&&budget.until<=now){budget.until=now+60000;budget.count=0;}
    if(!budget){
      // Keep the counter map bounded even under a flood of authenticated identities.
      if(budgets.size>=5000)return res.status(503).json({error:'Help is busy. Please try again shortly.'});
      budget={until:now+60000,count:0,active:0};budgets.set(key,budget);
    }
    if(budget.count>=maxPerMinute||budget.active>=1||active>=8){
      res.setHeader('Retry-After',String(Math.max(1,Math.ceil((budget.until-now)/1000))));
      return res.status(429).json({error:'Please wait a moment before asking again.'});
    }
    budget.count++;budget.active++;active++;
    try {const answer=await service.answer(req.body);const feedback=feedbackStore?.issue(answer,res.locals.helpActor);return res.json({...answer,...(feedback?{feedback}:{})});}
    catch {return res.status(503).json({error:'Help could not load an answer. Try again or browse a topic.'});}
    finally {budget.active--;active--;}
  });
  router.use((_req,res)=>res.status(404).json({error:'Unknown help route.'}));
  return router;
}
