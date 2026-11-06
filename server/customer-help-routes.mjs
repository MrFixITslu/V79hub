import {Router} from 'express';
import {createHelpService,helpCatalog,findArticle,validateQuestion} from './customer-help.mjs';

/** @param {{context?: (req: import('express').Request) => ({userId:string,organizationId:string}|null), sameOrigin?: (req: import('express').Request) => boolean, service?: ReturnType<typeof createHelpService>, clock?: () => number, maxPerMinute?: number}} options */
export function customerHelpRouter({context,sameOrigin,service=createHelpService(),clock=Date.now,maxPerMinute=12}={}) {
  const router=Router();
  // No question/history/answer persistence. These are expiring rate counters only.
  const budgets=new Map();
  let active=0;
  router.use((req,res,next)=>{
    res.setHeader('Cache-Control','no-store');
    const actor=context?.(req);
    if(!actor?.userId||!actor?.organizationId) return res.status(401).json({error:'Sign in to Hub to use app help.'});
    res.locals.helpActor=actor;next();
  });
  router.get('/catalog',(_req,res)=>res.json(helpCatalog()));
  router.get('/articles/:id',(req,res)=>{
    const article=findArticle(req.params.id);
    return article?res.json({article}):res.status(404).json({error:'This help article is unavailable.'});
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
    try {return res.json(await service.answer(req.body));}
    catch {return res.status(503).json({error:'Help could not load an answer. Try again or browse a topic.'});}
    finally {budget.active--;active--;}
  });
  router.use((_req,res)=>res.status(404).json({error:'Unknown help route.'}));
  return router;
}
