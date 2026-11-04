import copy,hashlib,json,unittest
import generation_views as G

class Views(unittest.TestCase):
    def setUp(self):
        self.p=lambda name:'/nix/store/'+'a'*32+'-'+name
        self.state={'schema_version':1,'system':self.p('old-system'),'active_slot':'blue','adopted':self.p('old-adopted'),
            'slots':{s:{k:self.p(s+'-'+k) for k in ('server','runtime')} for s in ('blue','green')}}
        self.raw=json.dumps(self.state,sort_keys=True).encode()
        self.candidate={'schema_version':1,'slot':'green','adopted':self.p('new-adopted'),'bundle':self.p('bundle'),
            'proposal_sha256':'c'*64,'deployment_authorized':False}
        self.bundle={'schema_version':1,'slot':'green','proposal_sha256':'c'*64,'deployment_authorized':False,
            'server':self.p('new-server'),'runtime':self.p('new-runtime')}
        a={'schema_version':1,'phase':'current','candidatePath':self.p('candidate'),
            'input_state_sha256':hashlib.sha256(self.raw).hexdigest(),'state':copy.deepcopy(self.state),
            'assertions_pass':True,'units':{u:'a'*64 for u in ('mrjam-rust-blue.service','mrjam-rust-green.service','nginx-config-reload.service','postgresql.service')},
            'routes_sha256':'a'*64,'adopted':self.state['adopted'],'no_implicit_restart':True,
            **{f:{s:'a'*64 for s in ('blue','green')} for f in ('slot_services','non_asset_configurations','asset_routes')}}
        b=copy.deepcopy(a);b.update(phase='stage');b['state']['system']=self.p('staged-system')
        b['state']['slots']['green']={k:self.bundle[k] for k in ('server','runtime')}
        b['units']['mrjam-rust-green.service']='b'*64;b['slot_services']['green']='b'*64
        c=copy.deepcopy(b);c.update(phase='promotion',adopted=self.candidate['adopted'],routes_sha256='b'*64)
        c['state'].update(system=self.p('new-system'),active_slot='green',adopted=self.candidate['adopted'])
        c['units']['nginx-config-reload.service']='b'*64;c['units']['mrjam-rust-blue.service']='b'*64
        self.views={'current':a,'stage':b,'promotion':c}
    def verify(self):return G.verify(self.views,self.state,self.raw,self.p('candidate'),self.candidate,self.bundle)
    def test_exact_views_preserve_all_eleven_gates(self):
        result=self.verify();self.assertEqual(len(result['checks']),11);self.assertTrue(all(result['checks'].values()))
        self.assertFalse(result['deployment_authorized'])
    def test_platform_delivery_preserves_vise_and_rejects_lost_adoption(self):
        self.state['vise']={'artifact':self.p('vise-artifact'),'adopted':self.p('vise-adopted')}
        self.raw=json.dumps(self.state,sort_keys=True).encode()
        for view in self.views.values():
            view['state']['vise']=copy.deepcopy(self.state['vise'])
            view['input_state_sha256']=hashlib.sha256(self.raw).hexdigest()
        result=self.verify()
        self.assertEqual(result['promotedState']['vise'],self.state['vise'])
        del self.views['promotion']['state']['vise']
        with self.assertRaisesRegex(Exception,'GENERATION_OUTPUT_STATE_REFUSED'):self.verify()
    def test_mixed_inputs_and_candidate_paths_refused(self):
        for field,value in [('input_state_sha256','f'*64),('candidatePath',self.p('other')),('phase','current')]:
            with self.subTest(field=field):
                original=self.views['stage'][field];self.views['stage'][field]=value
                with self.assertRaisesRegex(Exception,'GENERATION_VIEW_BINDING_REFUSED'):self.verify()
                self.views['stage'][field]=original
    def test_every_semantic_gate_rejects_corruption(self):
        original=copy.deepcopy(self.views)
        changes=[('current',('state','system'),self.p('unexpected-current')),
            ('stage',('assertions_pass',),False),('stage',('units','postgresql.service'),'b'*64),
            ('stage',('units','extra.service'),'b'*64),('stage',('routes_sha256',),'b'*64),
            ('stage',('adopted',),self.p('wrong-adopted')),
            ('stage',('non_asset_configurations','green'),'b'*64),('stage',('asset_routes','green'),'b'*64),
            ('promotion',('units','postgresql.service'),'b'*64),('promotion',('slot_services','green'),'c'*64),
            ('promotion',('no_implicit_restart',),False)]
        for phase,path,value in changes:
            with self.subTest(phase=phase,path=path):
                self.views=copy.deepcopy(original);target=self.views[phase]
                for key in path[:-1]:target=target[key]
                target[path[-1]]=value
                with self.assertRaises(Exception):self.verify()
    def test_candidate_cannot_replace_active_slot(self):
        self.candidate['slot']='blue'
        with self.assertRaisesRegex(Exception,'GENERATION_CANDIDATE_REFUSED'):self.verify()
    def test_missing_view_refused(self):
        self.views.pop('stage')
        with self.assertRaisesRegex(Exception,'GENERATION_VIEWS_REFUSED'):self.verify()
    def test_unbound_output_state_refused(self):
        self.views['promotion']['state']['slots']['blue']['server']=self.p('unbound')
        with self.assertRaisesRegex(Exception,'GENERATION_OUTPUT_STATE_REFUSED'):self.verify()
    def test_non_boolean_flags_refused(self):
        self.views['promotion']['no_implicit_restart']=1
        with self.assertRaisesRegex(Exception,'GENERATION_VIEW_SHAPE_REFUSED'):self.verify()
    def test_missing_unit_is_not_ignored(self):
        self.views['promotion']['units'].pop('postgresql.service')
        with self.assertRaisesRegex(Exception,'GENERATION_INVARIANT_REFUSED'):self.verify()
    def test_control_plane_is_preserved_across_delivery(self):
        control={'preparation':self.p('preparation'),'acceptance':self.p('acceptance'),'staging':self.p('staging')}
        self.state['control_plane']=control;self.raw=json.dumps(self.state,sort_keys=True).encode()
        for v in self.views.values():
            v['state']['control_plane']=dict(control)
            v['input_state_sha256']=hashlib.sha256(self.raw).hexdigest()
        self.assertEqual(self.verify()['promotedState']['control_plane'],control)
        self.views['promotion']['state']['control_plane']['acceptance']=self.p('other-acceptance')
        with self.assertRaisesRegex(Exception,'GENERATION_OUTPUT_STATE_REFUSED'):self.verify()
    def test_unknown_control_plane_fields_refused(self):
        self.state['control_plane']={'command':'arbitrary'}
        with self.assertRaisesRegex(Exception,'GENERATION_CONTROL_PLANE_REFUSED'):self.verify()
    def test_stack_cannot_disappear_or_change_during_app_delivery(self):
        control={n:self.p(n) for n in ('preparation','acceptance','staging','stack')}
        self.state['control_plane']=control;self.raw=json.dumps(self.state,sort_keys=True).encode()
        for v in self.views.values():
            v['state']['control_plane']=dict(control)
            v['input_state_sha256']=hashlib.sha256(self.raw).hexdigest()
        self.assertEqual(self.verify()['promotedState']['control_plane'],control)
        self.views['promotion']['state']['control_plane'].pop('stack')
        with self.assertRaisesRegex(Exception,'GENERATION_OUTPUT_STATE_REFUSED'):self.verify()
        self.views['promotion']['state']['control_plane']['stack']=self.p('old-stack')
        with self.assertRaisesRegex(Exception,'GENERATION_OUTPUT_STATE_REFUSED'):self.verify()

if __name__=='__main__':unittest.main()
