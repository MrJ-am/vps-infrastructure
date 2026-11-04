import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import promotion_service as S

class Layout(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.state=self.root/'state';self.state.mkdir(mode=0o700)
        self.plan={'schema_version':1,'job':'a'*64,'proposal_sha256':'b'*64,'slot':'blue','bundle':'/nix/store/'+'c'*32+'-bundle',
            'old':str(self.root/'old'),'new':str(self.root/'new'),'forge_pull':2,'review':{}}
        self.marker={'schema_version':1,'proposal_sha256':'b'*64,'plan_sha256':'d'*64}
        for target,port in [('old',38102),('new',38101)]:
            base=self.root/target;(base/'etc/nginx').mkdir(parents=True);(base/'etc/systemd/system').mkdir(parents=True)
            (base/'etc/nginx/nginx.conf').write_text(('proxy_pass http://127.0.0.1:'+str(port)+';\n')*11)
            for slot in ['blue','green']:
                (base/('etc/systemd/system/mrjam-rust-'+slot+'.service')).write_text(
                    '[Service]\nExecStart=/nix/store/'+'a'*32+'-server/bin/mrjam-server serve --config /nix/store/'+'b'*32+'-runtime/runtime.json\nUser=synthetic\n')
        (self.state/'plan.json').write_text(json.dumps(self.plan))
        # Root ownership and generation identifier checks are exercised by
        # reservation tests. This fixture isolates byte-level layout checks.
        for obj,name,replacement in [(S.C,'regular_file',lambda p,**kw:Path(p).read_bytes()),
                (S.R,'identity',lambda p:self.marker),(S.Adapter,'retained',lambda a:{'synthetic':'unchanged'})]:
            patcher=patch.object(obj,name,replacement);patcher.start();self.addCleanup(patcher.stop)
    def adapter(self):return S.Adapter(self.state)
    def test_exact_port_only_transition_retains_both_slot_commands(self):
        p=self.root/'new/etc/systemd/system/mrjam-rust-blue.service'
        p.write_text(p.read_text()+'\n[Install]\nWantedBy=multi-user.target\n')
        a=self.adapter();self.assertEqual(a.slots,{'new':'blue','old':'green'})
    def test_unrelated_nginx_change_refused_before_any_command(self):
        p=self.root/'new/etc/nginx/nginx.conf';p.write_text(p.read_text()+'unexpected configuration\n')
        with patch.object(S,'run') as run:
            with self.assertRaisesRegex(Exception,'PROMOTION_ROUTE_DIFF_REFUSED'):self.adapter()
            run.assert_not_called()
    def test_slot_privilege_change_refused_before_any_command(self):
        p=self.root/'new/etc/systemd/system/mrjam-rust-blue.service';p.write_text(p.read_text().replace('User=synthetic','User=root'))
        with patch.object(S,'run') as run:
            with self.assertRaisesRegex(Exception,'PROMOTION_SLOT_COMMAND_CHANGED'):self.adapter()
            run.assert_not_called()
    def test_unsigned_or_changed_payload_cannot_reach_activation(self):
        a=self.adapter()
        with patch.object(S,'credential',return_value='synthetic'),patch.object(S.V,'verify',side_effect=S.C.Refused('BAD_SIGNATURE')),patch.object(S,'run') as run:
            with self.assertRaisesRegex(Exception,'BAD_SIGNATURE'):a.authorize()
            run.assert_not_called()
    def test_bundle_for_other_slot_command_refused(self):
        a=self.adapter()
        with patch.object(S,'credential',return_value='synthetic'),patch.object(S.V,'verify',return_value={'server':'wrong','runtime':'wrong'}):
            with self.assertRaisesRegex(Exception,'PROMOTION_UNBOUND_SLOT'):a.authorize()
    def test_vise_is_not_a_blocking_precondition(self):
        self.assertNotIn('vise',S.UNITS)
        seen=[]
        class Connection:
            def __init__(self,host,*args,**kwargs):
                if host=='vise.mrj.am':raise OSError('synthetic ViSe unavailable')
                seen.append(host)
            def request(self,*args,**kwargs):pass
            def getresponse(self):return self
            status=200
            def read(self,*args):return b''
            def close(self):pass
        with patch.object(S.http.client,'HTTPSConnection',Connection):S.public_health()
        self.assertEqual(len(seen),6);self.assertNotIn('vise.mrj.am',seen)

if __name__=='__main__':unittest.main()
