import copy,unittest
import staging_layout as L

class Layout(unittest.TestCase):
    def setUp(self):
        old={'a.service':'masked','a.service.d':'directory','a.service.d/overrides.conf':'fixed',
            'mrjam-rust-blue.service':'blue','mrjam-rust-green.service':'old-green',
            'multi-user.target.wants/mrjam-rust-blue.service':'blue'}
        staged={**old,'mrjam-rust-green.service':'new-green'}
        promoted={**staged,'nginx-config-reload.service':'new-route'}
        promoted.pop('multi-user.target.wants/mrjam-rust-blue.service')
        promoted['multi-user.target.wants/mrjam-rust-green.service']='new-green'
        self.trees={'old':old,'staged':staged,'promoted':promoted}
    def test_unchanged_masks_and_dropins_with_only_inactive_slot_change(self):L.compare(self.trees,'green')
    def test_unmasking_another_service_refused(self):
        self.trees['staged']['a.service']='unmasked'
        with self.assertRaisesRegex(Exception,'STAGING_BUILT_UNIT_CHANGED'):L.compare(self.trees,'green')
    def test_changed_or_added_dropin_refused(self):
        for name in ['a.service.d/overrides.conf','mrjam-rust-green.service.d/unexpected.conf']:
            trees=copy.deepcopy(self.trees);trees['staged'][name]='changed'
            with self.assertRaisesRegex(Exception,'STAGING_BUILT_UNIT_CHANGED'):L.compare(trees,'green')
    def test_stage_cannot_change_public_slot_boot_links(self):
        self.trees['staged'].pop('multi-user.target.wants/mrjam-rust-blue.service')
        with self.assertRaisesRegex(Exception,'STAGING_BUILT_UNIT_CHANGED'):L.compare(self.trees,'green')
    def test_promotion_cannot_change_unrelated_service(self):
        self.trees['promoted']['postgresql.service']='changed'
        with self.assertRaisesRegex(Exception,'STAGING_PROMOTION_UNIT_CHANGED'):L.compare(self.trees,'green')

if __name__=='__main__':unittest.main()
