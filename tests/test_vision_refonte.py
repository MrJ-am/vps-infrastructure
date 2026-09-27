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
 def test_migration_additive_conserve_donnees_et_prepare_les_seances(self):
  source=self.d/'source';(source/'migrations').mkdir(parents=True)
  (source/'migrations/013_observations_seances.sql').write_text('migration 013')
  (source/'migrations/014_items_contenu.sql').write_text('migration 014')
  with patch.object(m,'empreinte_donnees',side_effect=[{'seances':'avant'},{'seances':'avant'}]),patch.object(m,'psql',side_effect=[b'2',b'2',b'',b'',b'2',b'2',b'2',b'58',b'f',b'20']) as sql,patch.object(m,'proprietaire',return_value='alice'):
   rapport=m.migration_sequentielle(source,'isolée')
  self.assertTrue(rapport['donnees_preservees'])
  self.assertEqual(rapport['seances_ouvertes_preservees'],2)
  self.assertEqual(rapport['seances_de_test'],0)
  self.assertEqual(rapport['items_autonomes_verifies'],58)
  self.assertEqual(rapport['migrations'],[13,14])
  self.assertEqual([c.args[1] for c in sql.call_args_list if c.args[1].startswith('migration ')],['migration 013','migration 014'])
 def test_migration_additive_refuse_une_alteration(self):
  source=self.d/'source';(source/'migrations').mkdir(parents=True)
  (source/'migrations/013_observations_seances.sql').write_text('migration 013')
  (source/'migrations/014_items_contenu.sql').write_text('migration 014')
  with patch.object(m,'empreinte_donnees',side_effect=[{'seances':'avant'},{'seances':'apres'}]),patch.object(m,'psql',return_value=b'2'):
   with self.assertRaisesRegex(RuntimeError,'Une donnée mémorielle'):
    m.migration_sequentielle(source,'isolée')
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

class Candidat(unittest.TestCase):
 def test_archives_exactes_et_manifeste(self):
  import hashlib,zipfile
  racine=Path(__file__).resolve().parents[1];p=racine/'operations/vision-refonte-candidat.json'
  if not p.exists():self.skipTest('Branche préparatoire sans artefacts')
  d=json.loads(p.read_text())
  self.assertEqual(set(d['fichiers']),{'vendor/vision-refonte-source.tar.gz','vendor/vision-refonte-interface.zip'})
  for n,h in d['fichiers'].items():self.assertEqual(hashlib.sha256((racine/n).read_bytes()).hexdigest(),h)
  with tarfile.open(racine/'vendor/vision-refonte-source.tar.gz','r:gz') as t:
   self.assertEqual(t.extractfile('revision-application.txt').read().decode().strip(),d['application'])
   for f in t.getmembers():self.assertTrue(f.isfile() and not f.name.startswith('/') and '..' not in Path(f.name).parts)
  with zipfile.ZipFile(racine/'vendor/vision-refonte-interface.zip') as z:
   manifeste=json.loads(z.read('manifest.json'));self.assertEqual(manifeste['revisionApplication'],d['application'])
   self.assertEqual({n for n in z.namelist() if not n.endswith('/')},set(manifeste['fichiers'])|{'manifest.json'})
   for n,h in manifeste['fichiers'].items():self.assertEqual(hashlib.sha256(z.read(n)).hexdigest(),h)
