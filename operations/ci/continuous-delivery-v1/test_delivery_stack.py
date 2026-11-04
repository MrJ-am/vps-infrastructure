import copy
import unittest
import delivery_stack as S

class Stack(unittest.TestCase):
    def setUp(self):
        self.packages={n:'/nix/store/'+'a'*32+'-'+n for n in S.COMMANDS}
        self.descriptor=dict(schema_version=1,deployment_authorized=False,enableVise=True,packages=self.packages)
        self.control={n:self.packages[n] for n in ('preparation','acceptance','staging')}
        self.units={unit:'[Service]\nExecStart='+self.packages[name]+'/bin/'+exe+'\n'
            for name,commands in S.COMMANDS.items() for unit,exe in commands.items()}
    def verify(self):return S.verify(self.descriptor,self.units,self.control)
    def test_complete_stack(self):self.assertEqual(self.verify(),self.packages)
    def test_each_stale_or_missing_service_refused(self):
        original=copy.deepcopy(self.units)
        for unit in original:
            for replacement in ('',original[unit].replace('a'*32,'b'*32),original[unit]+'ExecStart=/bin/true\n'):
                with self.subTest(unit=unit,replacement=replacement):
                    self.units=dict(original);self.units[unit]=replacement
                    with self.assertRaisesRegex(Exception,'DELIVERY_STACK_UNIT_REFUSED'):self.verify()
    def test_control_cannot_select_different_packages(self):
        self.control['acceptance']=self.packages['promotion']
        with self.assertRaisesRegex(Exception,'DELIVERY_STACK_CONTROL_REFUSED'):self.verify()
    def test_queue_condition_must_match_enabled_mode(self):
        self.descriptor['enableVise']=False
        with self.assertRaisesRegex(Exception,'DELIVERY_STACK_QUEUE_MODE_REFUSED'):self.verify()
        self.units['mrjam-promotion.service']+='ConditionPathExists=/var/lib/mrjam-promotion/plan.json\n'
        self.verify()
        self.descriptor['enableVise']=True
        with self.assertRaisesRegex(Exception,'DELIVERY_STACK_QUEUE_MODE_REFUSED'):self.verify()
    def test_invalid_descriptor_refused(self):
        original=copy.deepcopy(self.descriptor)
        for field,value in [('schema_version',True),('deployment_authorized',True),('enableVise',1),('extra',False),('packages',{})]:
            with self.subTest(field=field):
                self.descriptor=copy.deepcopy(original);self.descriptor[field]=value
                with self.assertRaises(Exception):self.verify()

if __name__=='__main__':unittest.main()
