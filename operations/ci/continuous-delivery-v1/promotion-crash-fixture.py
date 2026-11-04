"""Synthetic VM only: separate durable files and real process termination."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,'/etc/promotion-synthetic')
import promotion_transaction as P
root=Path(os.environ['STATE_DIRECTORY']);cut=int(os.environ['CASE_INDEX'])
assert 0<=cut<=100
def read(name,default):
    p=root/(name+'.json')
    return json.loads(p.read_bytes()) if p.exists() else default
def save(name,value):
    tmp=root/(name+'.next');dst=root/(name+'.json')
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(json.dumps(value).encode());out.flush();os.fsync(out.fileno())
    os.replace(tmp,dst);fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)

class Adapter:
    def event(self,name):
        value=read('events',{'count':0,'crashed':False,'history':[]})
        value['count']+=1;value['history'].append(name);save('events',value)
        if value['count']==cut and not value['crashed']:
            value['crashed']=True;save('events',value);os._exit(86)
    def phase(self):return read('journal',{'phase':'prepared'})['phase']
    def reserve(self):
        j=read('job',{'deployed':False,'marker':False})
        j['marker']=not j['deployed'];save('job',j);self.event('reserve')
    def authorize(self):self.event('authorize-synthetic')
    def ready(self,target):self.event('ready-'+target)
    def switch(self,target):
        m=read('machine',{'current':'old','boot':'old'});m['current']=target;save('machine',m);self.event('switch-'+target)
    def boot(self,target):
        m=read('machine',{'current':'old','boot':'old'});m['boot']=target;save('machine',m);self.event('boot-'+target)
    def verify(self,target,*,boot):
        m=read('machine',{'current':'old','boot':'old'});assert m['current']==target
        if boot:assert m['boot']==target
        self.event('verify-'+target+('-boot' if boot else ''))
    def checkpoint(self,phase):save('journal',{'phase':phase});self.event('checkpoint-'+phase)
    def commit_job(self):
        assert read('machine',{})=={'current':'new','boot':'new'}
        save('job',{'deployed':True,'marker':False});self.event('commit-job')
    def abort_job(self):
        assert read('machine',{})=={'current':'old','boot':'old'}
        save('job',{'deployed':False,'marker':False});self.event('abort-job')
    def verify_complete(self):
        assert read('machine',{})=={'current':'new','boot':'new'}
        assert read('job',{})=={'deployed':True,'marker':False}

a=Adapter();result=P.promote(a);assert result['code']=='PROMOTION_COMPLETE';a.verify_complete()
events=read('events',{})
save('proof',{'complete':True,'cut':cut,'events':events['count'],'crashed':events['crashed'],
    'synthetic_only':True,'separate_durable_files':True})
