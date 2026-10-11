"""Une qualification de composant ne touche pas les checkouts étrangers à ses entrées."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import frontends
import assemblage


class SourcesFrontend(unittest.TestCase):
    def test_atelier_logo_borne_les_demarrages_navigateur(self):
        # Vérifie la commande réelle, sans lancer de navigateur dans cette unité.
        with patch.object(frontends.subprocess,'run') as executions:
            frontends.tester_frontend('style',self.sources,{},'complement')
        browsers=[a.args[0] for a in executions.call_args_list if 'test:browser' in a.args[0]]
        self.assertEqual([['npm','--prefix','ateliers/logo','run','test:browser','--','--workers=1']],browsers)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='frontends-sources-',dir=ROOT/'state')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.sources={cle:self.root/cle for cle in ['vps','style','signature','vision','matheval','logique']}
        self.m={'sources':{},'frontends':{}}
        self.patch=patch.object(frontends,'RACINE',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        self.depot('style',{'src/MrJam.elm':'module MrJam exposing (x)\nx = 1','public/index.html':'<div id="app"></div>',
                            'elm.json':'{}','identite.json':'{}'})
        self.depot('signature',{'ressource':'identite'})

    def depot(self,cle,fichiers):
        base=self.sources[cle];base.mkdir(exist_ok=True)
        subprocess.run(['git','init','--quiet',str(base)],check=True)
        for nom,contenu in fichiers.items():
            p=base/nom;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(contenu)
        subprocess.run(['git','add','.'],cwd=base,check=True)
        subprocess.run(['git','-c','user.name=Qualification','-c','user.email=qualification@example.invalid',
                        'commit','--quiet','-m','Fixture locale'],cwd=base,check=True)
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=base,text=True).strip()
        self.m['sources'][cle]={'revision':revision}
        return revision

    def test_style_ignore_les_consommateurs_absents(self):
        self.m['frontends']={'vision':{'verrou_style':'inaccessible'},'logique':{'verrou_style':'inaccessible'}}
        self.assertEqual({},frontends.preparer(self.sources,self.m,'style'))
        self.assertFalse(self.sources['vision'].exists())
        self.assertFalse(self.sources['logique'].exists())

    def test_construction_style_sans_cache_vision(self):
        # Le transport/build est stubé, le choix des commandes reste le vrai.
        # Cette fixture ne constitue aucune qualification d'une interface.
        scripts=self.root/'scripts';scripts.mkdir()
        (scripts/'revoir-frontends.py').write_text('def verifier(*arguments): pass\n')
        with patch.object(frontends.subprocess,'run') as executions, patch.object(frontends,'verifier_sources') as verifier, patch.object(frontends,'enregistrer_candidat',return_value={'fixture':True}):
            self.assertEqual({'fixture':True},frontends.construire_dans_atelier('style',self.sources,self.m,{}))
        self.assertEqual(3,executions.call_count)
        self.assertEqual({'style','signature'},set(verifier.call_args.args[0]))
        self.assertTrue(all(appel.kwargs['cwd']==self.sources['style'] for appel in executions.call_args_list))
        self.assertFalse(self.sources['vision'].exists())

    def test_producteur_modifie_refuse_sans_effacer_le_travail(self):
        source=self.sources['style']/'src/MrJam.elm';source.write_text('travail concurrent')
        with self.assertRaisesRegex(ValueError,'Source de publication modifiée : style'):
            frontends.preparer(self.sources,self.m,'style')
        self.assertEqual('travail concurrent',source.read_text())

    def test_generateur_ne_peut_pas_qualifier_des_sources_modifiees(self):
        scripts=self.root/'scripts';scripts.mkdir()
        (scripts/'revoir-frontends.py').write_text('def verifier(*arguments): pass\n')
        source=self.sources['style']/'public/index.html'
        execution_reelle=subprocess.run
        def generer(commande,**options):
            if commande[0] in ('npm','node'):
                source.write_text('générateur ayant changé une source suivie')
                return subprocess.CompletedProcess(commande,0)
            return execution_reelle(commande,**options)
        with patch.object(frontends.subprocess,'run',side_effect=generer), patch.object(frontends,'enregistrer_candidat') as candidat:
            with self.assertRaisesRegex(ValueError,'Source de publication modifiée : style'):
                frontends.construire_dans_atelier('style',self.sources,self.m,{})
            candidat.assert_not_called()
        self.assertEqual('générateur ayant changé une source suivie',source.read_text())

    def test_vision_prepare_uniquement_son_verrou_exact(self):
        revision=self.m['sources']['style']['revision']
        raw=json.dumps({'revision':revision}).encode()
        self.depot('vision',{'interface/style.lock.json':raw.decode(),'.gitignore':'interface/.dependances/\n'})
        self.m['frontends']={'vision':{'verrou_style':'interface/style.lock.json','revision_style':revision,
                                     'sha256':frontends.sha(raw),'origine_style':'MrJ-am/style-mrjam'},
                             'logique':{'verrou_style':'inaccessible'},'matheval':{'verrou_style':'inaccessible'}}
        caches=frontends.preparer(self.sources,self.m,'vision')
        self.assertEqual({'vision'},set(caches))
        self.assertEqual((self.sources['style']/'src/MrJam.elm').read_bytes(),
                         (self.sources['vision']/'interface/.dependances/style-mrjam/src/MrJam.elm').read_bytes())
        self.assertFalse(self.sources['logique'].exists())
        self.assertFalse(self.sources['matheval'].exists())
        self.m['frontends']['vision']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Contrat de style différent'):
            frontends.preparer(self.sources,self.m,'vision')

    def test_recu_identifie_le_style_consomme_et_son_invalidation(self):
        ancien=self.m['sources']['style']['revision']
        raw=json.dumps({'revision':ancien}).encode()
        self.depot('vision',{'interface/style.lock.json':raw.decode()})
        self.m['frontends']['vision']={'verrou_style':'interface/style.lock.json',
            'revision_style':ancien,'sha256':frontends.sha(raw)}
        suite={'entrees':{'style':['src/MrJam.elm']},'style_consomme_par':'vision'}
        with patch.object(assemblage,'manifeste',return_value=self.m), patch.object(assemblage,'environnement',return_value={'fixture':True}):
            avant=assemblage.identifiant_suite('fixture',suite,self.sources)
            # Publier une nouvelle tête ne remplace pas le verrou du consommateur.
            nouveau=self.depot('style',{'src/MrJam.elm':'module MrJam exposing (x)\nx = 2'})
            self.assertNotEqual(ancien,nouveau)
            self.assertEqual(avant,assemblage.identifiant_suite('fixture',suite,self.sources))
            raw=json.dumps({'revision':nouveau}).encode()
            (self.sources['vision']/'interface/style.lock.json').write_bytes(raw)
            self.m['frontends']['vision'].update(revision_style=nouveau,sha256=frontends.sha(raw))
            apres=assemblage.identifiant_suite('fixture',suite,self.sources)
            self.assertNotEqual(avant,apres)
            self.assertEqual(frontends.sha((self.sources['style']/'src/MrJam.elm').read_bytes()),
                apres['entrees']['style/src/MrJam.elm'])
