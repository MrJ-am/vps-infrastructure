"""Exercise unmodified coordinator control flow; model only OS/systemd boundaries.
No production paths are written and no subprocess/server is started here.
"""
import contextlib,json,sys,tempfile,unittest,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,os.environ['SOURCE_ROOT']+'/operations/continuous-delivery')
import deploy as D
import system_delivery as S
import migrations as M

class PowerCut(BaseException): pass

class Fixture:
 def __init__(self,fail=None,interrupt=False):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.stack=contextlib.ExitStack()
  self.fail=fail;self.interrupt=interrupt;self.fired=False;self.suppress_rollback=False;self.events=[];self.reloads=0
  self.state=self.root/'state';self.state.mkdir();self.control=self.root/'control';self.control.mkdir()
  self.packages={}
  for name in ['system-A','system-B','system-C','engine-A','engine-B','engine-C','controls-A','controls-B','controls-C','release-C']:
   path=self.root/name;path.mkdir();self.packages[name]=path
  for suffix in ['A','B','C']:
   for name in S.CONTROL_NAMES:(self.packages['controls-'+suffix]/(name+'.service')).write_text('[Service]\nExecStart=fixture-'+suffix+'\n')
   for name in ['nginx','forgejo','postgresql']:
    path=self.packages['system-'+suffix]/'etc/systemd/system'/(name+'.service');path.parent.mkdir(parents=True,exist_ok=True);path.write_text('[Service]\nExecStart='+name+'-'+suffix+'\n')
  self.system=str(self.packages['system-B']);self.profile=self.system
  self.engine=self.root/'engine';self.engine.symlink_to(self.packages['engine-B'])
  for name in S.CONTROL_NAMES:(self.control/(name+'.service')).symlink_to(self.packages['controls-B']/(name+'.service'))
  self.confA=self.root/'A.conf';self.confA.write_text('proxy_pass http://127.0.0.1:38101;')
  self.confB=self.root/'B.conf';self.confB.write_text('proxy_pass http://127.0.0.1:38102;')
  self.route=self.root/'nginx-current.conf';self.route.symlink_to(self.confB)
  self.exec={c:'/nix/store/'+c.lower()*32+'-server/bin/mrjam-server serve --config /nix/store/'+c.lower()*32+'-runtime/runtime.json' for c in ['A','B','C']}
  self.config={'blue':self.exec['A'],'green':self.exec['B']};self.running=dict(self.config)
  self.previousA={'revision':'a'*40,'output':str(self.packages['release-C']),'slot':'blue','configuration':str(self.confA)}
  self.transactionB={'format':2,'revision':'b'*40,'old_configuration':str(self.confA),'old_state':self.previousA,'old_system':str(self.packages['system-A']),
   'old_engine':str(self.packages['engine-A']),'old_controls':str(self.packages['controls-A']), 'old_slots':{'blue':self.exec['A'],'green':self.exec['A']},
   'compatible':True,'managed_units':['nginx','forgejo','postgresql'],'old_active_units':['nginx','forgejo','postgresql']}
  self.previousB={'format':2,'revision':'b'*40,'output':str(self.packages['release-C']),'slot':'green','configuration':str(self.confB),'rollback':self.transactionB,
   'schema_digests':{'server':'s','vise':'v'},'stateful_versions':{'postgresql':'17.11'}}
  D.atomic_json(self.state/'current.json',self.previousB)
  D.atomic_json(self.state/'baseline.json',{'schema_digest':'s','schema_digests':{'server':'s','vise':'v'},'stateful_versions':{'postgresql':'17.11'}})
  output=self.packages['release-C'];(output/'share/mrjam').mkdir(parents=True);(output/'share/mrjam/source-revision').write_text('c'*40)
  (output/'migrations').mkdir();(output/'migrations/plan.json').write_text('{"version":1,"steps":[]}')
  template=self.root/'candidate-template.conf';template.write_text('proxy_pass http://127.0.0.1:38101;\nadd_header X-Mrjam-Deployment "'+'c'*40+':blue";')
  self.manifest={'format':2,'revision':'c'*40,'system':str(self.packages['system-C']),'engine':str(self.packages['engine-C']),'controls':str(self.packages['controls-C']),
   'server':'/nix/store/'+'c'*32+'-server','nginx':'/nix/store/'+'d'*32+'-nginx','postgresql':'/nix/store/'+'e'*32+'-pg',
   'runtimes':{slot:'/nix/store/'+'c'*32+'-runtime' for slot in D.PORTS},'nginx_template':str(template),'managed_units':['nginx','forgejo','postgresql'],'stateful_versions':{'postgresql':'17.11'}}
  (output/'release.json').write_text(json.dumps(self.manifest));self.build={'format':2,'revision':'c'*40,'output':str(output),'schema_digests':{'server':'s','vise':'v'}}
 def at(self,event):
  self.events.append(event)
  if event==self.fail and not self.fired:
   self.fired=True;self.suppress_rollback=self.interrupt
   if self.interrupt:raise PowerCut(event)
   raise RuntimeError('injected '+event)
 def command(self,args,**kw):
  if args[0]=='nix-env':self.profile=args[-1];self.at('profile-set')
  elif args[0].endswith('/bin/switch-to-configuration'):
   self.at('activation-enter');self.system=str(Path(args[0]).parent.parent);self.at('activation-exit')
  elif args[:2]==['systemctl','show']:return 'active'
  elif args[:2]==['systemctl','restart']:
   unit=args[-1]
   if unit.startswith('mrjam-rust-'):
    slot=unit.removeprefix('mrjam-rust-').removesuffix('.service');self.running[slot]=self.config[slot];self.at('slot-restart')
   else:self.events.append('restart-'+unit)
  elif args[0].endswith('/bin/nginx'):self.at('nginx-validate')
  return ''
 def configure(self,slot,command):self.config[slot]=command
 def reload(self):
  self.reloads+=1;self.events.append('traffic-'+D.active_slot(self.route.read_text()));self.at('reload-'+str(self.reloads))
 def __enter__(self):
  original_rollback=S.rollback;original_apply=M.apply;original_prepare=M.prepare;original_resume=M.resume;original_atomic=D.atomic_json
  def rollback(*a,**kw):
   if self.suppress_rollback:raise PowerCut('coordinator gone; no exception handler runs')
   return original_rollback(*a,**kw)
  def apply(*a,**kw):result=original_apply(*a,**kw);self.at('migration-'+kw.get('phase','all'));return result
  def prepare(*a,**kw):result=original_prepare(*a,**kw);self.at('migration-prepare');return result
  def resume(*a,**kw):self.at('migration-resume');return original_resume(*a,**kw)
  def atomic(path,value):
   original_atomic(path,value)
   if path==self.state/'current.json' and value.get('revision')=='c'*40:self.at('current-written')
  values=[(D,'STATE',self.state),(D,'BOOT_READY',self.root/'boot-ready'),(D,'NGINX_CONF',self.route),(S,'PRIMARY',self.root/'primary'),(S,'ENGINE',self.engine),(S,'CONTROL',self.control),
   (S,'store_path',lambda value:Path(value)),(S,'retain',lambda *args:None),(S,'current_system',lambda:self.system),(D,'slot_command',lambda slot:self.config[slot]),
   (D,'configure_slot',self.configure),(D,'command',self.command),(D,'reload_nginx',self.reload),(D,'probe',lambda *args:True),(S,'check_public_services',lambda:self.at('public-services')),
   (S,'public_check',lambda *args:self.at('public-cutover')),(S,'rollback',rollback),(M,'prepare',prepare),(M,'apply',apply),(M,'resume',resume),(M,'LEDGER',self.root/'receipts.json'),(D,'atomic_json',atomic),
   (D,'api',lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('Recovery called Forgejo')))]
  for obj,name,value in values:self.stack.enter_context(patch.object(obj,name,value))
  return self
 def __exit__(self,*args):self.stack.close();self.tmp.cleanup()
 def restoredB(self,test):
  test.assertEqual(self.system,str(self.packages['system-B']));test.assertEqual(self.profile,self.system)
  test.assertEqual(self.config,{'blue':self.exec['A'],'green':self.exec['B']});test.assertEqual(self.running,self.config)
  test.assertEqual(self.route.resolve(),self.confB);test.assertEqual(json.loads((self.state/'current.json').read_text()),self.previousB)
  test.assertFalse((self.state/'transaction.json').exists())

class Independent(unittest.TestCase):
 def test_real_promote_control_flow_and_both_successive_rollbacks(self):
  with Fixture() as f:
   S.promote(f.build)
   self.assertEqual(D.active_slot(f.route.read_text()),'blue')
   state=json.loads((f.state/'current.json').read_text());D.rollback(state['rollback']);f.restoredB(self)
   D.rollback(f.transactionB);self.assertEqual(f.route.resolve(),f.confA);self.assertEqual(f.running['blue'],f.exec['A'])
 def test_preparation_and_activation_failures_restore_slots_and_generation(self):
  for point in ['migration-prepare','migration-before-system','nginx-validate','profile-set','activation-enter','activation-exit','migration-after-system','slot-restart','public-services','reload-2','public-cutover']:
   with self.subTest(point=point),Fixture(fail=point) as f:
    with self.assertRaises(RuntimeError):S.promote(f.build)
    f.restoredB(self)
    D.rollback(f.transactionB);self.assertEqual(f.running['blue'],f.exec['A']);self.assertEqual(f.route.resolve(),f.confA)
 def test_interruption_then_fresh_recovery_uses_only_local_journal(self):
  for point in ['migration-before-system','profile-set','activation-enter','activation-exit','migration-after-system','slot-restart','reload-2','public-cutover','current-written']:
   with self.subTest(point=point),Fixture(fail=point,interrupt=True) as f:
    with self.assertRaises(PowerCut):S.promote(f.build)
    self.assertTrue((f.state/'transaction.json').exists())
    f.suppress_rollback=False;D.recover();f.restoredB(self)
 def test_boot_recovery_keeps_journal_until_old_generation_has_booted(self):
  with Fixture(fail='activation-exit',interrupt=True) as f:
   with self.assertRaises(PowerCut):S.promote(f.build)
   f.suppress_rollback=False;original=f.command;reboots=[]
   def command(args,**kwargs):
    if args[0].endswith('/bin/switch-to-configuration') and args[1]=='boot':
     f.events.append('old-generation-selected-for-boot');return ''
    if args[:2]==['systemctl','reboot']:
     reboots.append(args);return ''
    return original(args,**kwargs)
   with patch.object(D,'command',side_effect=command):
    with self.assertRaisesRegex(RuntimeError,'previous system generation at boot'):D.restore()
    self.assertEqual(f.system,str(f.packages['system-C']))
    self.assertEqual(f.profile,str(f.packages['system-B']))
    self.assertTrue((f.state/'transaction.json').exists())
    self.assertEqual(len(reboots),1)
    f.system=str(f.packages['system-B']);f.running=dict(f.config)
    D.restore();f.restoredB(self)

 def test_phases_and_resume_surround_activation_and_cutover(self):
  with Fixture() as f:
   S.promote(f.build)
   names=['migration-prepare','migration-before-system','activation-enter','activation-exit','migration-after-system','public-cutover','migration-resume']
   positions=[f.events.index(x) for x in names];self.assertEqual(positions,sorted(positions))

@unittest.skipUnless(os.environ.get('MRJAM_TEST_MIGRATION_PROGRAM'),'Nix real migration program required')
class IndependentRealPrograms(unittest.TestCase):
 def program(self,f,phase='before-system'):
  (f.root/'.synthetic').touch()
  step={'id':'synthetic_vendor','driver':'program','scope':'server','compatibility':'maintenance',
        'package':os.environ['MRJAM_TEST_MIGRATION_PROGRAM'],'phase':phase}
  path=f.packages['release-C']/'migrations/plan.json';path.write_text(json.dumps({'version':1,'steps':[step]}))
  return step
 def test_real_after_system_program_obeys_activation_order(self):
  with Fixture() as f,patch.dict(os.environ,MRJAM_MIGRATION_FIXTURE=str(f.root)):
   self.program(f,'after-system')
   original=M.run_program
   def program(step,action):f.events.append('action-'+action);return original(step,action)
   with patch.object(M,'run_program',side_effect=program):S.promote(f.build)
   self.assertLess(f.events.index('action-quiesce'),f.events.index('activation-enter'))
   self.assertLess(f.events.index('activation-exit'),f.events.index('action-apply'))
   self.assertLess(f.events.index('public-cutover'),f.events.index('action-resume'))
 def test_real_program_recovers_after_coordinator_interruption_before_resume(self):
  with Fixture(fail='activation-exit',interrupt=True) as f,patch.dict(os.environ,MRJAM_MIGRATION_FIXTURE=str(f.root)):
   self.program(f)
   with self.assertRaises(PowerCut):S.promote(f.build)
   f.suppress_rollback=False;D.recover();f.restoredB(self)
   self.assertFalse((f.root/'changed').exists())
   self.assertEqual((f.root/'calls').read_text().splitlines(),['quiesce','apply','verify','recover'])
 def test_real_resume_failure_parks_without_restoring_new_data(self):
  with Fixture() as f,patch.dict(os.environ,MRJAM_MIGRATION_FIXTURE=str(f.root)):
   self.program(f);(f.root/'fail_resume').touch()
   template=Path(f.manifest['nginx_template']);template.write_text(template.read_text()+'\nserver_name vision.mrj.am;\n')
   with self.assertRaises(Exception):S.promote(f.build)
   self.assertTrue((f.root/'changed').exists())
   self.assertTrue((f.root/'paused').exists())
   self.assertTrue((f.state/'manual-recovery.json').exists())
   self.assertIn('return 503;',f.route.read_text())
   self.assertNotIn('recover',(f.root/'calls').read_text().splitlines())
   self.assertEqual(f.system,str(f.packages['system-C']))
 def test_real_interruption_after_commit_uses_conservative_write_boundary(self):
  with Fixture(fail='current-written',interrupt=True) as f,patch.dict(os.environ,MRJAM_MIGRATION_FIXTURE=str(f.root)):
   self.program(f)
   template=Path(f.manifest['nginx_template']);template.write_text(template.read_text()+'\nserver_name vision.mrj.am;\n')
   with self.assertRaises(PowerCut):S.promote(f.build)
   f.suppress_rollback=False
   with self.assertRaises(RuntimeError):D.recover()
   self.assertTrue((f.root/'changed').exists())
   self.assertTrue((f.state/'manual-recovery.json').exists())
   self.assertNotIn('recover',(f.root/'calls').read_text().splitlines())

if __name__=='__main__':unittest.main(verbosity=2)
