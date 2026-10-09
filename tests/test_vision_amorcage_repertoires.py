"""Refuser toute règle ou commande de répertoire hors de la création prévue."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
s = importlib.util.spec_from_file_location('repertoires', ROOT/'scripts/vision-amorcage-repertoires.py')
repertoires = importlib.util.module_from_spec(s);s.loader.exec_module(repertoires)
s = importlib.util.spec_from_file_location('essai', ROOT/'scripts/vision-identite-amorcage-activer.py')
essai = importlib.util.module_from_spec(s);s.loader.exec_module(essai)


class Repertoires(unittest.TestCase):
    def fixture(self, racine):
        ancien = racine/'ancien'; nouveau = racine/'nouveau'
        for systeme in (ancien,nouveau):
            (systeme/'etc/systemd/system').mkdir(parents=True);(systeme/'etc/tmpfiles.d').mkdir()
            (systeme/'etc/systemd/system'/repertoires.UNITE).write_text('[Unit]\nX-Restart-Triggers='+str(systeme)+'\n[Service]\nExecStart=systemd-tmpfiles --create --remove --exclude-prefix=/dev\n')
            (systeme/'etc/tmpfiles.d/nixos.conf').write_text('d /var/lib/vision 0700 vision vision -\n')
            (systeme/'etc/tmpfiles.d/base.conf').write_text('d /run/fixture 0755 root root -\n')
        with (nouveau/'etc/tmpfiles.d/nixos.conf').open('a') as f:f.write(repertoires.REGLE+'\n')
        return ancien,nouveau

    def test_une_creation_seule_et_declencheur_different(self):
        with tempfile.TemporaryDirectory() as tmp:
            ancien,nouveau=self.fixture(Path(tmp))
            self.assertTrue(repertoires.verifier(ancien,nouveau,Path(tmp)))

    def test_regle_ancienne_modifiee_retiree_ou_nouveau_chemin_refuses(self):
        for contenu in ('d /var/lib/vision 0777 root root -\n'+repertoires.REGLE+'\n',
                repertoires.REGLE+'\n', 'd /var/lib/vision 0700 vision vision -\nr /var/lib/vision/donnees - - - -\n'+repertoires.REGLE+'\n',
                'd /var/lib/vision 0700 vision vision -\n'+repertoires.REGLE.replace('0700','0755')+'\n'):
            with tempfile.TemporaryDirectory() as tmp:
                ancien,nouveau=self.fixture(Path(tmp));(nouveau/'etc/tmpfiles.d/nixos.conf').write_text(contenu)
                with self.assertRaises(ValueError):repertoires.verifier(ancien,nouveau,Path(tmp))

    def test_nouveau_fichier_commande_modifiee_et_symlink_externe_refuses(self):
        for modification in ('fichier','absence','commande','symlink'):
            with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as externe:
                ancien,nouveau=self.fixture(Path(tmp))
                if modification=='fichier':(nouveau/'etc/tmpfiles.d/ajout.conf').write_text(repertoires.REGLE+'\n')
                elif modification=='absence':(nouveau/'etc/tmpfiles.d/base.conf').unlink()
                elif modification=='commande':(nouveau/'etc/systemd/system'/repertoires.UNITE).write_text('[Unit]\nX-Restart-Triggers=autre\n[Service]\nExecStart=commande-inattendue\n')
                else:
                    p=Path(externe)/'prive';p.write_text('d /run/fixture 0755 root root -\n')
                    cible=nouveau/'etc/tmpfiles.d/base.conf';cible.unlink();cible.symlink_to(p)
                with self.assertRaises(ValueError):repertoires.verifier(ancien,nouveau,Path(tmp))

    def test_dry_arret_resetup_exige_la_preuve_et_ne_permet_pas_reload(self):
        prefixe='would activate the configuration...\n'
        arret=prefixe+'would stop the following units: '+repertoires.UNITE+'\n'
        with self.assertRaises(RuntimeError):essai.verifier_dry(arret)
        self.assertEqual(essai.verifier_dry(arret,True),1)
        for action in ('reload','restart'):
            with self.assertRaises(RuntimeError):essai.verifier_dry(prefixe+'would '+action+' the following units: '+repertoires.UNITE+'\n',True)
        with self.assertRaises(RuntimeError):essai.verifier_dry(prefixe+'would stop the following units: sshd.service\n',True)


if __name__ == '__main__':unittest.main()
