"""Contrats de publication : intégrité, schéma, concurrence et retour sans SQL."""
import io,json,sys,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import publication_interfaces as m

class Publication(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.d=Path(t.name)
  self.avant={'systeme':'g','demarrage':'g','configuration':'c',**{p:'ancien-'+p for p in m.PROJETS}}
  self.r={'avant':self.avant,'publications':{p:'nouveau-'+p for p in m.PROJETS},'fichiers':{}}
  (self.d/'preparation.json').write_text(json.dumps(self.r))
  for objet,nom,valeur in [(m,'dossier',self.d),(m.v,'etat',self.avant),(m.v,'services',None),(m,'executer',b''),(m,'publier_matheval',None)]:
   p=patch.object(objet,nom,return_value=valeur);p.start();self.addCleanup(p.stop)
 def test_artefacts_reels(self):m.verifier(Path(__file__).resolve().parents[1])
 def test_archive_sortante_refusee(self):
  p=self.d/'archive.tar.gz'
  with tarfile.open(p,'w:gz') as t:
   n=tarfile.TarInfo('../secret');n.size=1;t.addfile(n,io.BytesIO(b'x'))
  with self.assertRaises(RuntimeError):m.lire_tar(p)
 def test_doublon_refuse(self):
  p=self.d/'archive.tar.gz'
  with tarfile.open(p,'w:gz') as t:
   for _ in range(2):n=tarfile.TarInfo('x');n.size=1;t.addfile(n,io.BytesIO(b'x'))
  with self.assertRaises(RuntimeError):m.lire_tar(p)
 def test_concurrence_refusee_avant_activation(self):
  with patch.object(m.v,'etat',return_value={**self.avant,'vision':'tiers'}):
   with self.assertRaises(RuntimeError):m.appliquer('a'*40)
  m.executer.assert_not_called();m.publier_matheval.assert_not_called()
 def test_ancien_timer_enregistre_sans_effet(self):
  (self.d/'enregistre').touch();m.retour('a'*40)
  m.executer.assert_not_called();m.publier_matheval.assert_not_called()
 def test_retour_refuse_une_publication_exterieure(self):
  (self.d/'engage').touch()
  with patch.object(m.v,'etat',return_value={**self.avant,'logique':'tiers'}),patch.object(m.v,'lien') as lien:
   with self.assertRaises(RuntimeError):m.retour('a'*40)
   lien.assert_not_called()
 def test_retour_retablit_trois_apps_sans_sql(self):
  (self.d/'engage').touch()
  with patch.object(m.v,'etat',return_value=m.attendu(self.r)),patch.object(m.v,'lien') as lien:m.retour('a'*40)
  self.assertEqual(lien.call_count,3);m.publier_matheval.assert_called_once_with(self.avant['matheval'])
  self.assertTrue(all(c.args[0]=='systemctl' for c in m.executer.call_args_list))
  self.assertFalse(json.loads((self.d/'retour.json').read_text())['restauration_base'])
 def test_finalisation_refusee_sans_essai(self):
  with self.assertRaises(RuntimeError):m.finaliser('a'*40)
  self.assertFalse((self.d/'enregistre').exists())
 def test_fichier_metier_modifie_refuse(self):
  a=self.d/'a';b=self.d/'b'
  for p in (a,b):(p/'migrations').mkdir(parents=True)
  (a/'migrations/001.sql').write_text('ancien');(b/'migrations/001.sql').write_text('nouveau')
  with self.assertRaisesRegex(RuntimeError,'schéma changé'):m.preserver_metier({'vision':str(a)},{'vision':str(b)})
 def test_schema_fige_et_routes_seules_autorisees(self):
  a=self.d/'a';b=self.d/'b'
  for p in (a,b):
   (p/'src').mkdir(parents=True);(p/'src/server.lisp').write_text(str(p));(p/'src/mcp.lisp').write_text('identique')
  m.preserver_metier({'vision':str(a),'matheval':str(a)},{'vision':str(b),'matheval':str(b)})
