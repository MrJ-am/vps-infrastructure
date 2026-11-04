import copy
import unittest
import check_aligned_report as C

class Report(unittest.TestCase):
    def setUp(self):
        self.artifacts=[{'name':'server','bytes':1,'sha256':'a'*64},
                        {'name':'frontend.tar','bytes':2,'sha256':'b'*64}]
        self.report=C.expected(self.artifacts)

    def test_complete_exact_details_pass(self):
        C.check(self.report,self.artifacts)
        self.assertEqual(len(self.report['steps']),74)

    def test_missing_or_forged_detail_refused(self):
        for mode in ('missing','changed','extra'):
            value=copy.deepcopy(self.report)
            step=next(s for s in value['steps'] if 'base_sha256' in s)
            if mode=='missing':del step['base_sha256']
            elif mode=='changed':step['base_sha256']='0'*64
            else:step['candidate_exception']=True
            with self.assertRaises(ValueError):C.check(value,self.artifacts)

    def test_stale_source_missing_step_and_changed_artifact_refused(self):
        for mutate in [lambda v:v['steps'].pop(),
                       lambda v:v['sources'][0].update(revision='0'*40),
                       lambda v:v['artifacts'][0].update(sha256='0'*64),
                       lambda v:v.update(production_authorized=True),
                       lambda v:v.update(proposal_sha256='0'*64)]:
            value=copy.deepcopy(self.report);mutate(value)
            with self.assertRaises(ValueError):C.check(value,self.artifacts)

if __name__=='__main__':unittest.main()
