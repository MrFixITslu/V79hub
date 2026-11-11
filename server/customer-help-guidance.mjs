// Pure, deterministic navigation over reviewed customer text. No tools, records,
// identity, generated instructions, persistence or operational side effects.
const stages=new Set(['before','step','check','blocked','solved']);
const actions={before:['next','blocked'],step:['next','back','blocked'],check:['back','solved','blocked'],blocked:['retry','back','restart'],solved:['restart']};
export function validateGuide(guide,articles,currentVersion) {
  if(!guide||typeof guide!=='object'||Array.isArray(guide)||Object.keys(guide).some(k=>!['articleId','version','stage','index','action'].includes(k)))return 'Choose a valid guide action.';
  const article=articles.get(guide.articleId);
  if(!article||typeof guide.version!=='string'||guide.version.length>100)return 'Choose a documented guide and version.';
  if(guide.action==='start')return Object.keys(guide).some(k=>!['articleId','version','action'].includes(k))?'Start a guide without previous step state.':null;
  if(!stages.has(guide.stage)||!actions[guide.stage]?.includes(guide.action)||!Number.isInteger(guide.index)||guide.index< -1||guide.index>100)return 'This guide step or action is unavailable.';
  // An old article may have had more steps. Never navigate obsolete state;
  // buildGuide will restart at the current prerequisites instead.
  if(guide.version!==currentVersion)return null;
  if(!stages.has(guide.stage)||!actions[guide.stage]?.includes(guide.action)||!Number.isInteger(guide.index)||guide.index<(guide.stage==='blocked'?-1:0)||guide.index>(guide.stage==='blocked'?article.steps.length:article.steps.length-1))return 'This guide step or action is unavailable.';
  if(guide.stage==='before'&&guide.index!==0||['check','solved'].includes(guide.stage)&&guide.index!==article.steps.length-1)return 'This guide step is inconsistent.';
  return null;
}
export function guideLink(article) {
  const view=article.app==='hub'?({'1.1':'overview','1.2':'connections','1.3':'team','1.4':'security','1.5':'billing'}[article.section]||'connections'):'connections';
  return {href:`/?view=${view}`,label:article.app==='hub'?'Open this Hub section':'Open My Apps'};
}
export function buildGuide(article,version,request) {
  let stage=request.stage,index=request.index;
  const changed=request.version!==version;
  if(changed||request.action==='start'||request.action==='restart'){stage='before';index=0;}
  else if(request.action==='blocked'){index=stage==='before'?-1:stage==='check'?article.steps.length:index;stage='blocked';}
  else if(request.action==='solved')stage='solved';
  else if(request.action==='retry'){
    if(index===-1){stage='before';index=0;}
    else if(index===article.steps.length){stage='check';index=article.steps.length-1;}
    else stage='step';
  }
  else if(request.action==='next'){
    if(stage==='before')stage='step';
    else if(index<article.steps.length-1)index++;
    else stage='check';
  } else if(request.action==='back'){
    if(stage==='check')stage='step';
    else if(index>0){index--;stage='step';}
    else {stage='before';index=0;}
  }
  const text=stage==='before'||index===-1?article.before:stage==='check'||index===article.steps.length?article.check:stage==='solved'?'You marked this as resolved. I have not checked your workspace.':article.steps[index];
  const heading={before:'Before you start',step:`Step ${index+1} of ${article.steps.length}`,check:'Check the result',blocked:index===-1?'Cannot start yet':index===article.steps.length?'Result does not match':`Stuck at step ${index+1}`,solved:'Marked as resolved'}[stage];
  const question={before:'Are you ready to begin?',step:'Were you able to complete this step?',check:'Does this match what you see?',blocked:'You can review an earlier step or prepare a support summary. Check the app before repeating any save, payment or submission.',solved:'You can start a new question whenever you need help.'}[stage];
  const labels={next:stage==='before'?'Start steps':stage==='step'&&index===article.steps.length-1?'Check my result':'Done, next step',back:'Previous step',blocked:stage==='before'?'I cannot start':'I am stuck',solved:'Yes, resolved',retry:'Review this step',restart:'Restart guide'};
  return {articleId:article.id,version,stage,index,total:article.steps.length,heading,text,question,changed,link:guideLink(article),
    actions:actions[stage].map(action=>({action,label:labels[action]}))};
}
export function diagnoseProblem(message,app) {
  // Clarification selects a documented task, never asserts a root cause.
  const problem=/\b(?:cannot|can.t|unable|stuck|failed|fails|error|missing|rejected|wrong|doesn.t|didn.t|won.t|not working|not saving|not publishing|not loading|not showing)\b/i;
  if(!problem.test(message))return null;
  if(app==='academy'&&/sign.?in|log.?in|password|access|open/i.test(message))return {question:'Is the problem signing into Academy or finding your course progress?',choices:[['Learner sign-in or password','manual-6-2'],['Course access or progress','manual-6-3']]};
  if(app==='marketing'&&/post|publish|deliver|schedule|connect|account/i.test(message))return {question:'Is the problem the social connection or a scheduled post?',choices:[['Social account connection or readiness','manual-5-7'],['Scheduled post or delivery result','manual-5-6']]};
  if(app==='ffpro'&&/import|receipt|statement|extract|upload/i.test(message))return {question:'Are you reviewing an import or checking the resulting transactions?',choices:[['Receipt or statement import','manual-4-3'],['Saved transactions in Money','manual-4-2']]};
  if(/launch|load|sign.?in|log.?in|access|open|missing app/i.test(message)&&!/\b(?:register|till|project|transaction|job|campaign|calendar|course)\b/i.test(message))return {question:'Where does app access stop?',choices:[['Launching an assigned app','manual-1-2'],['App assignment or team invitation','manual-1-3'],['Plan or payment access','manual-1-5'],['Academy learner sign-in','manual-6-2']]};
  return null;
}
export const vagueProblem=/^(?:(?:i |we )?(?:am |are )?(?:stuck|need help)|(?:it|this|that)(?: still)? (?:doesn.t|didn.t|won.t|cannot|can.t|isn.t) (?:work|save|open|load)|(?:it|this|that) (?:failed|is missing)|(?:i |we )?(?:can.t|cannot) (?:save|continue|find it)|what next|where do i click)[?.!\s]*$/i;
