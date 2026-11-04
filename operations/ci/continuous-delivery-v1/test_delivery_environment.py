import unittest
import delivery_environment as E

class Environment(unittest.TestCase):
    def setUp(self):
        self.p=lambda n:'/nix/store/'+'a'*32+'-'+n
        self.units={'mrjam-rust-'+s+'.service':'[Service]\nExecStart='+self.p(s+'-server')+'/bin/mrjam-server serve --config '+self.p(s+'-runtime')+'/runtime.json\n' for s in E.SLOTS}
        self.routes=b'proxy_pass http://127.0.0.1:38101;\n'*11
    def parse(self,boot=None):return E.parse(self.p('system'),boot or self.p('system'),self.p('adopted'),self.routes,self.units)
    def control(self):
        self.units[E.PREPARATION]='[Service]\nExecStart='+self.p('preparation')+'/bin/mrjam-delivery-prepare\n'
        for s in E.STAGES:self.units['mrjam-acceptance-'+s+'.service']='ExecStart='+self.p('acceptance')+'/bin/mrjam-acceptance-'+s+'\n'
    def test_original_host_does_not_invent_control_plane(self):
        s=self.parse();self.assertNotIn('control_plane',s);self.assertEqual(s['active_slot'],'blue')
    def test_vise_adoption_binds_exact_installed_command(self):
        self.units['vise.service']='ExecStart='+self.p('vise-artifact')+'/server\n'
        state=E.parse(self.p('system'),self.p('system'),self.p('adopted'),self.routes,self.units,vise_adopted=self.p('vise-adopted'))
        self.assertEqual(state['vise'],{'artifact':self.p('vise-artifact'),'adopted':self.p('vise-adopted')})
    def test_vise_adoption_without_service_is_refused(self):
        with self.assertRaisesRegex(Exception,'DELIVERY_ENVIRONMENT_VISE_REFUSED'):
            E.parse(self.p('system'),self.p('system'),self.p('adopted'),self.routes,self.units,vise_adopted=self.p('vise-adopted'))
    def test_green_host_is_detected(self):
        self.routes=self.routes.replace(b'38101',b'38102');self.assertEqual(self.parse()['active_slot'],'green')
    def test_installed_packages_are_bound_as_data(self):
        self.control();self.assertEqual(self.parse()['control_plane'],{'preparation':self.p('preparation'),'acceptance':self.p('acceptance')})
    def test_complete_stack_is_bound_and_mixed_services_refused(self):
        packages={n:self.p(n) for n in E.S.COMMANDS}
        for name,commands in E.S.COMMANDS.items():
            for unit,exe in commands.items():self.units[unit]='ExecStart='+packages[name]+'/bin/'+exe+'\n'
        descriptor=dict(schema_version=1,deployment_authorized=False,enableVise=True,packages=packages)
        def read():return E.parse(self.p('system'),self.p('system'),self.p('adopted'),self.routes,self.units,
            installed_stack=(self.p('stack'),descriptor))
        self.assertEqual(read()['control_plane'],{**{n:packages[n] for n in ('acceptance','preparation','staging')},'stack':self.p('stack')})
        self.units['mrjam-validation-authority.service']=self.units['mrjam-validation-authority.service'].replace('/bin/','/old/')
        with self.assertRaisesRegex(Exception,'DELIVERY_STACK_UNIT_REFUSED'):read()
    def test_mixed_acceptance_versions_refused(self):
        self.control();self.units['mrjam-acceptance-merge.service']=self.units['mrjam-acceptance-merge.service'].replace('acceptance/bin','different/bin')
        with self.assertRaisesRegex(Exception,'DELIVERY_ENVIRONMENT_MIXED_ACCEPTANCE'):self.parse()
    def test_staging_package_is_included_in_protected_state(self):
        self.control();self.units[E.STAGING]='ExecStart='+self.p('staging')+'/bin/mrjam-delivery-stage\n'
        self.assertEqual(self.parse()['control_plane']['staging'],self.p('staging'))
    def test_orphan_staging_service_refused(self):
        self.units[E.STAGING]='ExecStart='+self.p('staging')+'/bin/mrjam-delivery-stage\n'
        with self.assertRaisesRegex(Exception,'DELIVERY_ENVIRONMENT_ORPHAN_STAGING'):self.parse()
    def test_boot_transition_refused(self):
        with self.assertRaisesRegex(Exception,'DELIVERY_ENVIRONMENT_NOT_STABLE'):self.parse(self.p('other'))
    def test_ambiguous_routes_refused(self):
        self.routes+=b'127.0.0.1:38102'
        with self.assertRaisesRegex(Exception,'DELIVERY_ENVIRONMENT_ROUTES_REFUSED'):self.parse()
    def test_extra_command_arguments_refused(self):
        self.units['mrjam-rust-blue.service']=self.units['mrjam-rust-blue.service'].replace('/runtime.json\n','/runtime.json --unexpected\n')
        with self.assertRaisesRegex(Exception,'DELIVERY_ENVIRONMENT_SLOT_REFUSED'):self.parse()

if __name__=='__main__':unittest.main()
