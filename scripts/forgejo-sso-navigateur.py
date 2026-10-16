#!/usr/bin/env python3
"""Anonymous production browser probes; never ask for the owner's MFA secret."""
import argparse,json,os,pathlib,re,urllib.parse
from playwright.sync_api import sync_playwright
p=argparse.ArgumentParser();p.add_argument('--url',default='https://forge.mrj.am');p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
base=a.url.rstrip('/');proof={'url':base,'ownerInteractiveLoginPerformed':False,'tlsValidation':True}
with sync_playwright() as pw:
 browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'],proxy={'server':os.environ['HTTPS_PROXY']} if os.environ.get('HTTPS_PROXY') else None)
 context=browser.new_context(viewport={'width':390,'height':844});page=context.new_page()
 response=page.goto(base+'/user/login');assert response.status==200
 assert page.locator('input[name="password"],input[name="user_name"]').count()==0
 links=page.locator('a[href*="/user/oauth2/"]');assert links.count()==1
 assert links.first.get_attribute('href').endswith('/user/oauth2/Kanidm')
 csrf=page.evaluate('window.config.csrfToken')
 assert page.request.post(base+'/user/login',form={'_csrf':csrf,'user_name':'MrJam','password':'disabled-local-login-probe'}).status==403
 assert page.request.get(base+'/api/v1/user',headers={'Authorization':'Basic TXJKYW06ZGlzYWJsZWQtbG9jYWwtbG9naW4tcHJvYmU='}).status in (401,403)
 proof.update(onlyKanidmProvider=True,noPasswordForm=True,passwordPostDenied=True,basicPasswordDenied=True)
 requests=[]
 def capture(req):
  u=urllib.parse.urlsplit(req.url)
  if u.netloc=='log.mrj.am' and u.path=='/ui/oauth2':
   q=urllib.parse.parse_qs(u.query)
   requests.append(q.get('client_id')==['mrjam-forgejo'] and q.get('redirect_uri')==[base+'/user/oauth2/Kanidm/callback'] and q.get('code_challenge_method')==['S256'] and len(q.get('code_challenge',[''])[0])>=43 and bool(q.get('state')))
 page.on('request',capture);links.first.click();page.wait_for_url(re.compile(r'https://log\.mrj\.am/.*'))
 page.wait_for_load_state('load');assert requests and all(requests)
 proof.update(realIdpRedirect=True,pkceS256=True,identityProviderHost=urllib.parse.urlsplit(page.url).netloc)
 browser.close()
a.output.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))
