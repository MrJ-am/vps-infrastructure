"""Garde de bascule : preuves réelles, marques concurrentes et installation privée."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('activation',ROOT/'scripts/vision-essai-activer.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Activation(unittest.TestCase):
    def test_preparation_exacte_complete_et_sans_mutation(self):
        r=json.loads((ROOT/'operations/vision-essai-preparation-reelle.json').read_text())
        m.verifier_preparation(r,r['infrastructure'])
        for k,v in [('restauration_vision_reelle',False),('association_et_admin_isoles',False),
                ('retour_acl_rejoue',False),('entree_persistante_reproduite',False),
                ('timer_independant_repete',False),('generation_active_modifiee',True),
                ('inscriptions',True),('fichiers_interface',True),('version',True),
                ('vision','a'*40),('infrastructure','a'*40)]:
            d=copy.deepcopy(r);d[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.verifier_preparation(d,r['infrastructure'])

    def test_finalisation_refuse_echec_retour_ou_absence_preuve(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp)
            for n in ('commence','teste'):(d/n).write_text('1\n')
            m.verifier_finalisation(d)
            for n in ('echec','retour-commence','retour-termine','enregistre'):
                (d/n).write_text('1\n')
                with self.subTest(n=n),self.assertRaises(ValueError):m.verifier_finalisation(d)
                (d/n).unlink()
            (d/'teste').unlink()
            with self.assertRaises(ValueError):m.verifier_finalisation(d)

    @unittest.skipUnless(os.geteuid()==0,'Qualification root exécutée en CI')
    def test_installation_ne_suit_pas_de_lien_et_ne_remplace_rien(self):
        with tempfile.TemporaryDirectory(dir='/root') as tmp:
            d=Path(tmp);p=d/'generation/operateur'
            m.installer_prive(p,b'contenu exact',0o700)
            self.assertEqual(p.read_bytes(),b'contenu exact')
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o700)
            with self.assertRaises(FileExistsError):m.installer_prive(p,b'etranger')
            autre=d/'etranger';autre.mkdir();lien=d/'lien';lien.symlink_to(autre)
            with self.assertRaises(ValueError):m.installer_prive(lien/'fichier',b'refuse')
            self.assertFalse((autre/'fichier').exists())
            autre.chmod(0o777)
            with self.assertRaises(ValueError):m.installer_prive(autre/'fichier',b'refuse')


    def test_retour_au_boot_mais_pas_au_redemarrage_des_cibles_durant_test(self):
        spec=importlib.util.spec_from_file_location('reprise_activation',ROOT/'scripts/vision-essai-reprise.py')
        reprise=importlib.util.module_from_spec(spec);spec.loader.exec_module(reprise)
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);outils=d/'outils';outils.mkdir()
            for n in ('bash','cp','mkdir','ln','rm'):(outils/n).symlink_to(shutil.which(n))
            unite='vision-essai-retour-aaaaaaaaaaaa';volatile=d/'marque-volatile'
            recette=reprise.fichiers(d,outils,unite)
            for n,t in recette.items():(d/n).write_text(t)
            (d/'reprise-generateur.sh').chmod(0o700)
            wrapper=d/'generateur-essai.sh';wrapper.write_text(m.generateur_essai(d,outils,unite,volatile))
            (d/'commence').write_text('1\n');volatile.write_text('1\n')
            for boot in (False,True):
                if boot:volatile.unlink()
                sorties=[d/('sortie-'+str(boot)+str(i)) for i in range(3)]
                for p in sorties:p.mkdir()
                subprocess.run(['bash',str(wrapper),*map(str,sorties)],check=True,capture_output=True)
                self.assertEqual((sorties[0]/(unite+'.service')).read_text(),recette['reprise.service'])
                self.assertEqual((sorties[0]/'multi-user.target.wants'/(unite+'.service')).is_symlink(),boot)

    @unittest.skipUnless(os.geteuid()==0,'Qualification root exécutée en CI')
    def test_parent_backend_reellement_traversable_malgre_umask_prive(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);os.chown(d,0,65534);d.chmod(0o750)
            parent=d/'backend';ancien=os.umask(0o077)
            try:m.preparer_parent_backend(parent,65534)
            finally:os.umask(ancien)
            fichier=parent/'preuve';fichier.write_text('technique')
            os.chown(fichier,0,65534);fichier.chmod(0o440)
            def sans_privilege():os.setgid(65534);os.setuid(65534)
            r=subprocess.run(['/bin/cat',str(fichier)],capture_output=True,preexec_fn=sans_privilege)
            self.assertEqual(r.returncode,0);self.assertEqual(r.stdout,b'technique')
            parent.chmod(0o700)
            r=subprocess.run(['/bin/cat',str(fichier)],capture_output=True,preexec_fn=sans_privilege)
            self.assertNotEqual(r.returncode,0)

    def test_cadre_refus_ne_publie_ni_exception_ni_valeur_privee(self):
        try:m.exiger(False)
        except Exception as error:
            error.args=('contenu privé interdit au journal',)
            r=m.cadres_refus(error,'worker')
            self.assertEqual(r['phase'],'worker')
            self.assertTrue(r['cadres'])
            self.assertNotIn('privé',json.dumps(r))
            self.assertEqual(set(r['cadres'][0]),{'fichier','ligne'})


if __name__=='__main__':unittest.main()
