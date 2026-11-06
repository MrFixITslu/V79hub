import {useEffect, useRef, useState} from 'react';
import {ArrowUp, BookOpen, Check, Copy, MessageCircle, RotateCcw, Search, X} from 'lucide-react';
import './customer-app-help.css';
import {GuidedSteps,SupportSummary,type Guide,type GuideRequest} from './CustomerGuidedSupport';
import {HelpFeedback,HelpFeedbackReport,type FeedbackTicket,type FeedbackReason} from './CustomerHelpFeedback';

type AppId = 'hub'|'tiquet'|'pos'|'ffpro'|'marketing'|'academy'|'combatzone';
type Article = {id:string;app:AppId;section:string;title:string;route:string;summary:string;before:string;steps:string[];check:string;note:string};
type Topic = Pick<Article,'id'|'app'|'title'|'route'|'section'>;
type Suggestion = {label:string;app:AppId;articleId?:string;mode?:'guide'};
type HelpAnswer = {feedback?:FeedbackTicket;guide?:Guide;status:string;answer:string;app:AppId|null;articles:Article[];version:string;reviewedAt:string;engine:'manual'|'local-ai';suggestions:Suggestion[];support:{url:string;label:string;template:string}};
type Catalog = {feedback?:{enabled:boolean;workspace:boolean;all:boolean;reasons:FeedbackReason[]};apps:{id:AppId;name:string;description:string}[];articles:Topic[];version:string;reviewedAt:string};
type Turn = {id:number;question:string;response:HelpAnswer};
const examples = ['How do I create a Tiquet service request?', 'How do I open the POS register?', 'How do I import an FFPRO statement?', 'How do I schedule a Marketing post?'];


function answerText(answer:HelpAnswer) {
  return [answer.answer,...(answer.guide?[`${answer.guide.heading}: ${answer.guide.text}`,answer.guide.question]:[]),...answer.articles.flatMap(a=>[
    a.title,a.route,`Before you start: ${a.before}`,
    ...a.steps.map((s,i)=>`${i+1}. ${s}`),`Check the result: ${a.check}`,a.note,
    `Source: V79 customer guide · Manual v2 §${a.section} · reviewed ${answer.reviewedAt}`,
  ])].join('\n\n');
}

export function CustomerAppHelp() {
  const [catalog,setCatalog]=useState<Catalog|null>(null);
  const [catalogError,setCatalogError]=useState(false);
  const [reload,setReload]=useState(0);
  const [app,setApp]=useState<AppId|''>('');
  const [topicSearch,setTopicSearch]=useState('');
  const [screen,setScreen]=useState('');
  const [supportOpen,setSupportOpen]=useState(false);
  const [reportOpen,setReportOpen]=useState(false);
  const [conversationVersion,setConversationVersion]=useState(0);
  const [question,setQuestion]=useState('');
  const [turns,setTurns]=useState<Turn[]>([]);
  const [pending,setPending]=useState(false);
  const [error,setError]=useState('');
  const [expired,setExpired]=useState(false);
  const [copied,setCopied]=useState<number|string|null>(null);
  const [failed,setFailed]=useState<{message:string;app?:AppId;articleId?:string;guide?:GuideRequest}|null>(null);
  const input=useRef<HTMLTextAreaElement>(null);
  const log=useRef<HTMLDivElement>(null);
  const abort=useRef<AbortController|null>(null);
  const generation=useRef(0);
  const sequence=useRef(0);
  const copyTimer=useRef<ReturnType<typeof setTimeout>|null>(null);

  useEffect(()=>{
    const controller=new AbortController();
    setCatalogError(false);
    fetch('/api/help/catalog',{credentials:'same-origin',signal:controller.signal})
      .then(async r=>{
        if(r.status===401){setExpired(true);setError('Your session has expired. Sign in to Hub, then open App Help again.');throw Error('Session expired');}
        if(!r.ok)throw Error('Unavailable');
        const data=await r.json();
        if(!Array.isArray(data.apps)||!Array.isArray(data.articles))throw Error('Invalid guide');
        if(!controller.signal.aborted)setCatalog(data);
      }).catch(()=>{if(!controller.signal.aborted)setCatalogError(true);});
    return ()=>controller.abort();
  },[reload]);
  useEffect(()=>()=>{generation.current++;abort.current?.abort();if(copyTimer.current)clearTimeout(copyTimer.current);},[]);
  useEffect(()=>{
    const last=log.current?.querySelector<HTMLElement>('.help-turn:last-child');
    const target=last?.querySelector<HTMLElement>('.help-walkthrough')||last;
    if(log.current)log.current.scrollTop=target?Math.max(0,target.offsetTop-20):0;
  },[turns]);
  useEffect(()=>{if(pending&&log.current)log.current.scrollTop=log.current.scrollHeight;},[pending]);

  function reset() {
    generation.current++;abort.current?.abort();setPending(false);setTurns([]);setQuestion('');
    setError('');setFailed(null);setCopied(null);setScreen('');setSupportOpen(false);setConversationVersion(n=>n+1);input.current?.focus({preventScroll:true});
  }
  function chooseApp(value:AppId|'') {
    // A new topic cannot inherit the previous app's article or pending response.
    reset();setApp(value);setTopicSearch('');
  }
  async function ask(message:string,selectedApp?:AppId,articleId?:string,guide?:GuideRequest) {
    if(pending||expired||!message.trim()||message.length>1200)return;
    const thisGeneration=++generation.current;
    const controller=new AbortController();abort.current=controller;
    const timeout=setTimeout(()=>controller.abort(),15000);
    const selected=selectedApp||app||undefined;
    const last=turns.at(-1)?.response;
    const request={message:message.trim(),...(selected?{app:selected}:{}),
      ...((articleId||last?.articles[0]?.id)?{articleId:articleId||last?.articles[0]?.id}:{}),
      history:turns.slice(-6).map(t=>t.question),...(screen?{context:{articleId:screen}}:{}),...(guide?{guide}:{})};
    setPending(true);setError('');setFailed(null);setCopied(null);
    try {
      const response=await fetch('/api/help/chat',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},body:JSON.stringify(request),signal:controller.signal});
      if(thisGeneration!==generation.current)return;
      if(response.status===401){setExpired(true);throw Error('Your session has expired. Sign in to Hub, then open App Help again.');}
      const data=await response.json();
      if(!response.ok)throw Error(data.error||'Help is unavailable. Try again or browse a topic.');
      if(typeof data.answer!=='string'||!Array.isArray(data.articles)||!Array.isArray(data.suggestions))throw Error('The answer could not be read. Try again.');
      setTurns(previous=>[...previous.slice(-19),{id:++sequence.current,question:message.trim(),response:data}]);
      setQuestion('');
      if(data.app){setApp(data.app);if(screen&&catalog?.articles.find(t=>t.id===screen)?.app!==data.app)setScreen('');}
      input.current?.focus({preventScroll:true});
    } catch(e) {
      if(thisGeneration!==generation.current)return;
      setError(controller.signal.aborted?'The answer took too long. Try again or browse a topic.':e instanceof Error?e.message:'Help is unavailable. Please try again.');
      setFailed({message,app:selected,articleId,guide});
    } finally {
      clearTimeout(timeout);
      if(thisGeneration===generation.current)setPending(false);
    }
  }
  async function copy(text:string,id:number|string) {
    try {
      await navigator.clipboard.writeText(text);setCopied(id);
      if(copyTimer.current)clearTimeout(copyTimer.current);
      copyTimer.current=setTimeout(()=>setCopied(null),2500);
    } catch {setError('Copy is unavailable in this browser. Select and copy the text, or use the support link.');}
  }
  function startGuide(articleId:string,version:string,label='Walk me through this') {
    void ask(label,undefined,articleId,{articleId,version,action:'start'});
  }
  const latest=turns.at(-1)?.response;
  const topics=(catalog?.articles||[]).filter(t=>(!app||t.app===app)&&`${t.title} ${t.route}`.toLowerCase().includes(topicSearch.toLowerCase()));
  const appName=catalog?.apps.find(a=>a.id===app)?.name||'All apps';
  const supportPanel=<SupportSummary key={`${app||'all'}:${conversationVersion}`} appName={appName} screenName={catalog?.articles.find(t=>t.id===screen)?.route} turns={turns} open={supportOpen} onOpen={()=>setSupportOpen(true)} onClose={()=>setSupportOpen(false)} onCopy={text=>void copy(text,'report')} copied={copied==='report'} disabled={pending||expired} onTiquet={()=>void ask('Create a new service request','tiquet','manual-2-3')}/>;

  return <section className="app-help" aria-labelledby="app-help-heading">
    <header className="help-heading">
      <div><h1 id="app-help-heading">How can we help?</h1><p>Practical answers for your V79 apps, with the guide behind every step.</p></div>
      <div className="help-heading-actions">{catalog?.feedback?.workspace&&<button type="button" className="help-secondary" disabled={expired} onClick={()=>setReportOpen(v=>!v)}>Help feedback report</button>}<button type="button" className="help-secondary" onClick={reset} disabled={expired}><RotateCcw size={16} aria-hidden="true"/>New conversation</button></div>
    </header>
    {reportOpen&&!expired&&catalog?.feedback?.workspace&&<HelpFeedbackReport apps={catalog.apps} reasons={catalog.feedback.reasons} canReadAll={catalog.feedback.all} onExpired={message=>{setExpired(true);setError(message);}} onClose={()=>setReportOpen(false)}/>}
    <div className="help-controls">
      <label htmlFor="help-app">Help me with</label>
      <select id="help-app" value={app} onChange={e=>chooseApp(e.target.value as AppId|'')} disabled={expired}>
        <option value="">All apps</option>
        {(catalog?.apps||[]).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}
      </select>
      <span>Guidance only. Your app permissions still apply.</span>
    </div>
    <div className="help-screen-context">
      <label htmlFor="help-screen">Screen (optional)</label>
      <select id="help-screen" value={screen} disabled={pending||expired||!catalog} onChange={e=>{setScreen(e.target.value);setSupportOpen(false);}}>
        <option value="">Choose your screen</option>
        {(catalog?.articles||[]).filter(t=>!app||t.app===app).map(t=><option key={t.id} value={t.id}>{t.route}</option>)}
      </select>
      <small>Choose the screen you need help with. Help cannot see your screen or records.</small>
    </div>
    <div className="help-layout">
      <div className="help-chat">
        <div className="help-chat-title"><MessageCircle size={18} aria-hidden="true"/><h2>Ask about {appName==='All apps'?'your apps':appName}</h2></div>
        <div className="help-log" ref={log} role="log" aria-label="App help conversation" aria-live="polite" aria-relevant="additions" aria-busy={pending}>
          {!turns.length&&<div className="help-welcome">
            <BookOpen size={28} aria-hidden="true"/>
            <h3>A clear next step.</h3>
            <p>Ask how to complete a task, find a setting or understand a screen. I use the customer guide and will tell you when it does not cover the answer.</p>
            <div className="help-examples">{examples.map(q=><button type="button" key={q} disabled={pending||expired} onClick={()=>ask(q)}>{q}<ArrowUp size={15} aria-hidden="true"/></button>)}</div>
          </div>}
          {turns.map(turn=><div className="help-turn" key={turn.id}>
            <div className="help-question"><span className="help-sr">You asked: </span>{turn.question}</div>
            <article className="help-answer" aria-label="Guide answer">
              {!turn.response.guide&&<p>{turn.response.answer}</p>}
              {turn.response.articles.map(article=><div key={article.id} className="help-procedure">
                <h3>{article.title}</h3>
                <p className="help-route">{article.route}</p>
                {turn.response.guide?<>
                  <GuidedSteps guide={turn.response.guide} active={turn.id===turns.at(-1)?.id} pending={pending} expired={expired} onAction={(label,request)=>void ask(label,article.app,article.id,request)} onSupport={()=>setSupportOpen(true)}/>
                  <details className="help-full-procedure"><summary>Read the full procedure</summary>
                    <p><strong>Before you start</strong> {article.before}</p>
                    <ol>{article.steps.map((step,i)=><li key={i}>{step}</li>)}</ol>
                    <p><strong>Check the result</strong> {article.check}</p>
                  </details>
                </>:<>
                  <p><strong>Before you start</strong> {article.before}</p>
                  <ol>{article.steps.map((step,i)=><li key={i}>{step}</li>)}</ol>
                  <p className="help-check"><Check size={17} aria-hidden="true"/><span><strong>Check the result</strong> {article.check}</span></p>
                  {turn.id===turns.at(-1)?.id&&<button type="button" className="help-primary help-start-guide" disabled={pending||expired} onClick={()=>startGuide(article.id,turn.response.version)}>Walk me through this</button>}
                </>}
                {article.note&&<p className="help-note">{article.note}</p>}
                <details className="help-source"><summary><BookOpen size={14} aria-hidden="true"/>Source: Manual v2 · §{article.section}</summary><p>Customer guide reviewed {turn.response.reviewedAt}. {article.title}. These are documented procedures, not a live check of your workspace.</p></details>
              </div>)}
              <div className="help-answer-footer">
                <span>{turn.response.engine==='local-ai'?'Local AI matched this guide':'Customer guide'}</span>
                <button type="button" onClick={()=>copy(answerText(turn.response),turn.id)} aria-label={copied===turn.id?'Answer copied':'Copy answer'}>{copied===turn.id?<Check size={15}/>:<Copy size={15}/>} {copied===turn.id?'Copied':'Copy answer'}</button>
              </div>
              {turn.id===turns.at(-1)?.id&&turn.response.feedback&&<HelpFeedback key={turn.id} feedback={turn.response.feedback} disabled={pending||expired} onExpired={message=>{setExpired(true);setError(message);}}/>}
            </article>
          </div>)}
          {pending&&<div className="help-loading" role="status"><span/>Finding the right guide section…</div>}
        </div>
        {latest&&!latest.guide&&!pending&&!expired&&<div className="help-suggestions" aria-label="Related questions">{latest.suggestions.slice(0,4).map(s=><button type="button" key={s.articleId||s.app} onClick={()=>s.mode==='guide'&&s.articleId?startGuide(s.articleId,latest.version,s.label):ask(s.articleId?s.label:`Help with ${s.label}`,s.app,s.articleId)}>{s.label}</button>)}</div>}
        {error&&<div className="help-error" role="alert"><p>{error}</p>{failed&&!expired&&<button type="button" onClick={()=>ask(failed.message,failed.app,failed.articleId,failed.guide)} disabled={pending}>Try again</button>}{expired&&<a href="/">Sign in to Hub</a>}<button type="button" aria-label="Dismiss help error" onClick={()=>setError('')}><X size={17}/></button></div>}
        <form className="help-composer" aria-label="Ask app help" onSubmit={e=>{e.preventDefault();void ask(question);}}>
          <label htmlFor="help-question">Your question</label>
          <div><textarea ref={input} id="help-question" rows={2} maxLength={1200} placeholder="For example: How do I add a new client in Tiquet?" value={question} disabled={pending||expired} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();void ask(question);}}}/><button type="submit" aria-label="Send question" disabled={!question.trim()||pending||expired}><ArrowUp size={20} aria-hidden="true"/></button></div>
          <p id="help-privacy">Keep passwords, payment details and private records out of chat. Enter to send; Shift + Enter for a new line.</p>
        </form>
      </div>
      <aside className="help-guide" aria-label="Browse customer guide">
        <details open><summary><BookOpen size={18} aria-hidden="true"/>Browse the guide</summary>
          <label className="help-search" htmlFor="help-topic-search"><Search size={16} aria-hidden="true"/><span className="help-sr">Find a help topic</span><input id="help-topic-search" placeholder="Find a topic" value={topicSearch} onChange={e=>setTopicSearch(e.target.value)}/></label>
          {catalogError?<div className="help-catalog-error"><p>{expired?'Sign in again to load help topics.':'The topic list could not load. You can still try asking a question.'}</p>{!expired&&<button type="button" onClick={()=>setReload(r=>r+1)}>Reload guide</button>}</div>:!catalog?<p role="status">Loading topics…</p>:<ul className="help-topics">{topics.map(t=><li key={t.id}><button type="button" disabled={pending||expired} onClick={()=>ask(t.title,t.app,t.id)}><span>{t.title}</span><small>{catalog.apps.find(a=>a.id===t.app)?.name} · §{t.section}</small></button></li>)}</ul>}
          {catalog&&!topics.length&&<p className="help-empty">No matching topics. Try another phrase or choose All apps.</p>}
        </details>
        {!supportOpen&&supportPanel}
        {catalog&&<p className="help-version">Manual v2 · reviewed {catalog.reviewedAt}<br/>Instructions can change as apps are updated.</p>}
      </aside>
    </div>
    {supportOpen&&supportPanel}
  </section>;
}
