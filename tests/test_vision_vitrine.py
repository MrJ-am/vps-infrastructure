"""Le retour d’une vitrine conserve les écritures et refuse une publication tierce."""
import importlib.util
import json
from pathlib import Path
import tempfile
import hashlib
import zipfile
import shutil
import unittest
from unittest.mock import patch

RACINE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('vitrine',RACINE/'scripts/vision-vitrine-deployer.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Retour(unittest.TestCase):
    def test_retour_sans_sql_et_sans_restaurer_des_donnees(self):
        with tempfile.TemporaryDirectory() as temporaire:
            d=Path(temporaire);(d/'engage').touch()
            avant=dict(systeme='systeme',demarrage='systeme',configuration='empreinte',matheval='matheval',logique='logique',vision='ancien',**{'vision-interface':'ancienne-interface'})
            courant={**avant,'vision':'candidat','vision-interface':'interface-candidate'}
            r=dict(avant=avant,serveur='candidat',interface='interface-candidate')
            appels=[]
            with patch.object(m,'lire',return_value=(d,r)),patch.object(m,'etat',side_effect=lambda:dict(courant)),patch.object(m,'services'),patch.object(m,'contrat'),patch.object(m,'donnees',return_value={'vision_items':'trace-apres-la-publication'}),patch.object(m,'executer',side_effect=lambda *a,**k:appels.append(a)),patch.object(m.subprocess,'run'),patch.object(m.commun,'lien',side_effect=lambda cible,lien:courant.__setitem__('vision' if lien=='/srv/vision/current' else 'vision-interface',cible)):
                m.retour('a'*40)
            self.assertEqual(courant,avant)
            self.assertTrue(json.loads((d/'retour.json').read_text())['donnees_preservees'])
            self.assertFalse(json.loads((d/'retour.json').read_text())['restauration_base'])
            self.assertTrue(all(a[0]=='systemctl' for a in appels),appels)

    def test_publication_concurrente_refusee(self):
        with tempfile.TemporaryDirectory() as temporaire:
            d=Path(temporaire);(d/'engage').touch()
            avant=dict(systeme='s',demarrage='s',configuration='c',matheval='m',logique='l',vision='ancien',**{'vision-interface':'ancienne-interface'})
            with patch.object(m,'lire',return_value=(d,dict(avant=avant,serveur='candidat',interface='candidate'))),patch.object(m,'etat',return_value={**avant,'vision':'une-autre-publication'}),patch.object(m.subprocess,'run'),patch.object(m,'executer') as commandes:
                with self.assertRaisesRegex(RuntimeError,'Publication concurrente'):m.retour('a'*40)
                commandes.assert_not_called()

    def test_un_retour_desarme_ne_touche_plus_aux_services(self):
        with tempfile.TemporaryDirectory() as temporaire:
            d=Path(temporaire);(d/'enregistre').touch()
            with patch.object(m,'lire',return_value=(d,{})),patch.object(m,'executer') as commandes,patch.object(m.subprocess,'run') as processus:
                m.retour('a'*40)
                commandes.assert_not_called();processus.assert_not_called()

class Archives(unittest.TestCase):
    def charger(self):
        spec=importlib.util.spec_from_file_location('candidat_vitrine',RACINE/'scripts/vision-vitrine-candidat.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_artefact_reel_correspond_aux_sources_et_routes_actives(self):
        candidat=self.charger().verifier(RACINE)
        self.assertEqual(candidat['migrations'],[])

    def test_un_fichier_altere_dans_une_archive_refuse_le_transfert(self):
        # Même si quelqu’un recalcule l’empreinte extérieure, le manifeste issu
        # de la CI doit empêcher le remplacement d’une image de présentation.
        with tempfile.TemporaryDirectory() as temporaire:
            d=Path(temporaire);(d/'vendor').mkdir();(d/'operations').mkdir()
            shutil.copyfile(RACINE/'vendor/vision-vitrine-source.tar.gz',d/'vendor/vision-vitrine-source.tar.gz')
            fichier=d/'vendor/vision-vitrine-interface.zip'
            with zipfile.ZipFile(RACINE/'vendor/vision-vitrine-interface.zip') as original,zipfile.ZipFile(fichier,'w') as modifie:
                for nom in original.namelist():
                    contenu=original.read(nom)
                    if nom.endswith('/memoire.webp'):contenu=b'image-remplacee'
                    modifie.writestr(nom,contenu)
            candidat=json.loads((RACINE/'operations/vision-vitrine-candidat.json').read_text())
            candidat['fichiers']['vendor/vision-vitrine-interface.zip']=hashlib.sha256(fichier.read_bytes()).hexdigest()
            (d/'operations/vision-vitrine-candidat.json').write_text(json.dumps(candidat))
            with self.assertRaisesRegex(AssertionError,'Fichier compilé modifié'):
                self.charger().verifier(d)

if __name__=='__main__':unittest.main()
