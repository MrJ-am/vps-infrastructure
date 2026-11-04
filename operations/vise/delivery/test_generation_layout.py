import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ci/continuous-delivery-v1'))
import generation_layout as L

class Layout(unittest.TestCase):
    def setUp(self):
        self.old='/nix/store/'+'a'*32+'-old';self.new='/nix/store/'+'b'*32+'-new'
        self.unit='[Service]\nEnvironment="CARNET_DIST='+self.old+'/dist"\nExecStart='+self.old+'/server\nUser=etp_carnet\n'
    def test_exact_artifact_replacement(self):
        L.compare_service(self.unit,self.unit.replace(self.old,self.new),self.new)
    def test_identity_or_environment_change_refused(self):
        new=self.unit.replace(self.old,self.new)
        for text in [new.replace('User=etp_carnet','User=root'),new+'Environment=OTHER=1\n',new.replace('/dist','/other')]:
            with self.assertRaisesRegex(Exception,'VISE_SERVICE_CONFIGURATION_CHANGED'):L.compare_service(self.unit,text,self.new)
    def test_backup_or_database_unit_change_refused(self):
        for other in ['postgresql.service','mrjam-vise-backup.service','mrjam-rust-blue.service']:
            before={'vise.service':'old',other:'same'};after={'vise.service':'new',other:'changed'}
            with self.assertRaisesRegex(Exception,'VISE_OTHER_UNIT_CHANGED'):L.compare_units(before,after)
    def test_dropin_added_refused(self):
        with self.assertRaisesRegex(Exception,'VISE_UNIT_SET_CHANGED'):
            L.compare_units({'vise.service':'old'},{'vise.service':'new','vise.service.d/override.conf':'extra'})
    def test_wanted_link_resolves_changed_unit(self):
        names=['vise.service','multi-user.target.wants/vise.service']
        self.assertEqual(L.compare_units(dict.fromkeys(names,'old'),dict.fromkeys(names,'new')),sorted(names))

if __name__=='__main__':unittest.main()
