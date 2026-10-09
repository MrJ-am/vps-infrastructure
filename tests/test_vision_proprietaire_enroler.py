import importlib.util, unittest
from pathlib import Path
from unittest.mock import patch
s=importlib.util.spec_from_file_location('prive',Path(__file__).resolve().parents[1]/'scripts/vision-proprietaire-enroler.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Gate(unittest.TestCase):
 def setUp(self):
  self.p={'infrastructure':'a'*40,'systeme_amorcage':'nouveau'};self.c={'audit':{'systeme':'ancien'},'vision':'vision','style':'style'}
  self.a={'version':1,'infrastructure':'b'*40,'preparation':'a'*40,'systeme_amorcage':'nouveau','systeme_ancien':'ancien','vision':'vision','style':'style'}
  self.a.update({k:True for k in ('activation_reservee','generation_enregistree','retour_neutralise','copie_locale_chiffree','copie_froide_chiffree','postgres_prive','services_conserves')})
  self.a.update({k:False for k in ('mode_vision_oidc','inscriptions','identite_humaine')})
 def test_preuve_non_enregistree_ou_ouverte_refusee(self):
  m.gate('c'*40,self.a,self.p,self.c)
  for key in ('generation_enregistree','copie_froide_chiffree','services_conserves','inscriptions','identite_humaine'):
   with self.subTest(key=key),self.assertRaises(ValueError):m.gate('c'*40,{**self.a,key:not self.a[key]},self.p,self.c)
  for key in ('infrastructure','preparation','systeme_amorcage','vision'):
   with self.subTest(key=key),self.assertRaises(ValueError):m.gate('c'*40,{**self.a,key:'etranger'},self.p,self.c)
 def test_enveloppe_invalide_refusee_sans_acces_cle(self):
  with patch.object(m.os,'open') as appel:
   for data in (b'donnees en clair',b'c2VjcmV0',b''):
    with self.assertRaises(ValueError):m.dechiffrer(data,'/outil-age')
   appel.assert_not_called()
if __name__=='__main__':unittest.main()
