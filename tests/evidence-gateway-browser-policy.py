"""Synthetic Chromium regression. No live session, OAuth code or network request."""
from playwright.sync_api import sync_playwright
from pathlib import Path
import re
source=(Path(__file__).resolve().parents[1]/"server/evidence-gateway-owner-bridge.mjs").read_text()
current_policy=re.search(r'Content-Security-Policy\',"([^"\n]+)"',source)[1]
assert "form-action 'self' https://chatgpt.com;" in current_policy
assert "res.setHeader('Referrer-Policy','same-origin')" in source
HUB='https://hub.v79sl.com'
CALLBACK='https://chatgpt.com/connector/oauth/SYNTHETIC_TEST'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox'])
 for name,referrer,allow,expected in [('original-referrer','no-referrer',True,False),('original-csp','same-origin',False,False),('corrected-policy','same-origin',True,True)]:
  context=browser.new_context();page=context.new_page();seen=[];violations=[]
  page.on('console',lambda message: violations.append(message.text))
  page.on('request',lambda request: seen.append('callback') if request.url.startswith(CALLBACK) else None)
  cdp=context.new_cdp_session(page);cdp.send('Network.enable');cdp.send('Network.setBlockedURLs',{'urls':['https://chatgpt.com/*']})
  def route(r):
   request=r.request
   if request.url.startswith(CALLBACK):r.fulfill(status=200,content_type='text/html',body='<h1>SYNTHETIC_CALLBACK_REACHED</h1>');return
   if request.url.startswith(HUB):
    if request.method=='POST':
     seen.append(request.headers.get('origin','MISSING'))
     if request.headers.get('origin')!=HUB:r.fulfill(status=403,body='ORIGIN_DENIED');return
     r.fulfill(status=303,headers={'location':CALLBACK});return
    policy=current_policy if allow else current_policy.replace("form-action 'self' https://chatgpt.com;","form-action 'self';")
    r.fulfill(status=200,headers={'content-type':'text/html','referrer-policy':referrer,'content-security-policy':policy},body='<form method="post" action="/api/agent/evidence-gateway/authorize"><button>Allow synthetic test</button></form>');return
   r.abort()
  context.route('**/*',route)
  page.goto(HUB+'/synthetic-consent');page.get_by_role('button').click(no_wait_after=True);page.wait_for_timeout(500)
  assert ('callback' in seen)==expected,(name,seen,violations)
  if name=='original-referrer':assert seen[0]=='null',seen
  if name=='original-csp':assert seen==[HUB] and any('form-action' in text for text in violations),(seen,violations)
  if expected:assert seen==[HUB,'callback']
  print(name+'=PASS',flush=True);context.close()
 browser.close()
