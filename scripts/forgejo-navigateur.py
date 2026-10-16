#!/usr/bin/env python3
"""Real Chromium assertions. Credentials remain in a private file, never reported."""
import argparse, json, pathlib, re, urllib.parse, os
from playwright.sync_api import sync_playwright

def main():
 p=argparse.ArgumentParser()
 p.add_argument('--url',required=True);p.add_argument('--credentials',type=pathlib.Path,required=True)
 p.add_argument('--username',default='validation');p.add_argument('--repository',default='org-validation')
 p.add_argument('--output',type=pathlib.Path,required=True);p.add_argument('--chromium',default='/usr/bin/chromium')
 p.add_argument('--proxy',default=os.environ.get('HTTPS_PROXY'))
 a=p.parse_args();base=a.url.rstrip('/')
 text=a.credentials.read_text();m=re.search("generated random password is '(.*?)'",text)
 password=m.group(1) if m else text.strip()
 results={'url':base,'engine':'Chromium','tests':[],'javascriptErrors':[],'resourceErrors':[]}
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=a.chromium,headless=True,args=['--no-sandbox'],proxy={'server':a.proxy,'bypass':'127.0.0.1,localhost'} if a.proxy else None)
  context=browser.new_context(viewport={'width':1280,'height':900})
  page=context.new_page();page.on('pageerror',lambda e:results['javascriptErrors'].append(str(e)))
  page.on('console',lambda msg:results['javascriptErrors'].append(msg.text) if msg.type=='error' else None)
  page.on('response',lambda r:results['resourceErrors'].append({'status':r.status,'path':urllib.parse.urlsplit(r.url).path}) if r.status>=400 else None)
  page.on('requestfailed',lambda r:results['resourceErrors'].append({'failed':urllib.parse.urlsplit(r.url).path}))
  external=[]
  page.on('request',lambda r:external.append(r.url) if urllib.parse.urlsplit(r.url).scheme in ('http','https') and urllib.parse.urlsplit(r.url).netloc!=urllib.parse.urlsplit(base).netloc else None)
  page.goto(base+'/user/login');page.locator('input[name="user_name"]').fill(a.username)
  page.locator('input[name="password"]').fill(password)
  page.locator('form .button.primary').click();page.wait_for_load_state('load')
  assert '/user/login' not in page.url,'Login failed'
  prefix=f'{base}/{a.username}/{a.repository}/src/branch/main/'
  for width in (1280,390):
   page.set_viewport_size({'width':width,'height':900})
   for path in ('README.org','docs/mathematiques.org','docs/delimiteurs.org','docs/structure.org'):
    response=page.goto(prefix+path);assert response.status==200
    page.wait_for_load_state('load')
    markup=page.locator('.markup').first;assert markup.count()==1,'Rendered document missing'
    assert markup.locator('h1,h2,h3').count()>0,'Headings missing'
    math=markup.locator('.math');count=math.count()
    if count:
     page.wait_for_function("document.documentElement.dataset.orgMathjax === 'ready'",timeout=45000)
     assert markup.locator('mjx-container[jax="CHTML"]').count()==count,'MathJax did not typeset every Pandoc math node'
     assert markup.locator('mjx-mfrac').count()>0,'Fractions not composed'
     assert markup.locator('mjx-merror').count()==0,'MathJax parse error'
    if path=='docs/mathematiques.org':
     assert markup.locator('mjx-mtable').count()>0,'Matrix/align missing'
     assert '(1)' in markup.inner_text() and '(2)' in markup.inner_text(),'Equation numbers missing'
     assert re.search(r'Référence\s*:\s*\(1\)',markup.inner_text()),'Equation reference not composed'
     assert '???' not in markup.inner_text(),'Equation reference unresolved'
    if path=='docs/delimiteurs.org':assert count==5,'Pandoc Org delimiter support changed'
    if path=='docs/structure.org':
     assert markup.locator('table').count()>0 and markup.locator('pre').count()>0
     assert markup.locator('ul li').count()>=2
     assert not page.evaluate('Boolean(window.orgInjected)'),'HTML injection'
     assert markup.locator('script,[onerror],a[href^="javascript:"]').count()==0,'Unsafe HTML survived'
     assert 'root:x:' not in markup.inner_text(),'Pandoc read local files'
     images=markup.locator('img[src*="point.png"]');assert images.count()==1
     assert images.evaluate('(i)=>i.complete && i.naturalWidth>0'),'Image not loaded'
     href=markup.locator('a').filter(has_text='Accueil').get_attribute('href')
     assert href.endswith('/README.org'),'Relative document link not rewritten'
     linked=page.goto(urllib.parse.urljoin(page.url,href));assert linked.status==200
    if width==390:
     assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'),'Page overflows on mobile'
    results['tests'].append({'document':path,'width':width,'pandocMathNodes':count,'chtml':count>0})
  assert not external, 'External resources requested: '+repr(external)
  assert not results['javascriptErrors'],results['javascriptErrors']
  assert not results['resourceErrors'],results['resourceErrors']
  anonymous=browser.new_context();anon=anonymous.new_page()
  anon.goto(prefix+'README.org');assert '/user/login' in anon.url,'Private repository visible anonymously'
  anon.goto(base+'/user/sign_up');assert anon.locator('input[name="password"]').count()==0,'Public registration open'
  results['privateAnonymousDenied']=True;results['publicRegistrationDisabled']=True
  browser.close()
 a.output.write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
 print('Forgejo: real Chromium Org/CHTML, mobile, sanitization and privacy assertions passed')

if __name__=='__main__':main()
