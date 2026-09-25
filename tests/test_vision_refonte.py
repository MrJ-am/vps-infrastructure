"""Garde-fous de la migration réelle : états périmés, retour et archives."""
import importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('refonte',Path(__file__).resolve().parents[1]/'scripts/vision-refonte-deployer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Migration(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.d=Path(t.name);self.revision='b'*40
  self.avant=dict(systeme='generation',demarrage='generation',configuration='empreinte',vision='ancien',**{'vision-interface':'ancienne','matheval':'m','logique':'l'})
  self.r=dict(avant=self.avant,serveur='nouveau',interface='nouvelle',application='a'*40)
  (self.d/'preparation.json').write_text(json.dumps(self.r))
  p=patch.object(m,'dossier',return_value=self.d);p.start();self.addCleanup(p.stop)
  p=patch.object(m,'executer');self.commande=p.start();self.addCleanup(p.stop)
 def test_etat_perime_refuse_avant_arret(self):
  with patch.object(m,'etat',return_value={**self.avant,'vision':'autre'}):
   with self.assertRaisesRegex(RuntimeError,'État modifié'):m.appliquer(self.revision)
  self.commande.assert_not_called()
 def test_pas_de_finalisation_sans_essai(self):
  with self.assertRaisesRegex(RuntimeError,'Essai absent'):m.finaliser(self.revision)
  self.commande.assert_not_called()
 def test_ancien_timer_apres_publication_sans_effet(self):
  (self.d/'enregistre').touch()
  with patch.object(m.subprocess,'run') as p:m.retour(self.revision);p.assert_not_called()
  self.commande.assert_not_called()
 def test_retour_ne_remplace_pas_autre_publication(self):
  (self.d/'engage').touch()
  with patch.object(m,'etat',return_value={**self.avant,'vision':'autre'}),patch.object(m.subprocess,'run'):
   with self.assertRaisesRegex(RuntimeError,'Publication concurrente'):m.retour(self.revision)
  self.commande.assert_not_called()
 def test_retour_ne_restaure_jamais_la_base(self):
  (self.d/'engage').touch()
  with patch.object(m,'etat',return_value={**self.avant,'vision':'nouveau','vision-interface':'nouvelle'}),patch.object(m.subprocess,'run'),patch.object(m,'lien') as lien:
   m.retour(self.revision)
  self.assertEqual(lien.call_count,2)
  for appel in self.commande.call_args_list:self.assertEqual(appel.args[0],'systemctl')
  self.assertFalse(json.loads((self.d/'retour.json').read_text())['restauration_base'])
 def test_archive_ne_sort_pas_de_sa_destination(self):
  p=self.d/'source.tar.gz';cible=self.d/'destination';cible.mkdir()
  with tarfile.open(p,'w:gz') as t:
   f=tarfile.TarInfo('../interdit');f.size=1;t.addfile(f,io.BytesIO(b'x'))
  with self.assertRaisesRegex(RuntimeError,'non sûre'):m.decompresser(cible,p)
  self.assertFalse((self.d/'interdit').exists())
