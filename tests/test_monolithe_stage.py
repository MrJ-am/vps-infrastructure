"""Refus de bundle altéré, lien et provenance incohérente, sans accès VPS."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import assemblage
spec=importlib.util.spec_from_file_location('preparer',ROOT/'scripts/monolithe-preparer.py')
preparer=importlib.util.module_from_spec(spec);spec.loader.exec_module(preparer)
spec_stage=importlib.util.spec_from_file_location('stage',ROOT/'scripts/monolithe-stage.py')
stage=importlib.util.module_from_spec(spec_stage);spec_stage.loader.exec_module(stage)


class PromotionAmendement(unittest.TestCase):
    def test_candidat_anterieur_ou_en_attente_refuse_avant_transport(self):
        for statut in (None,'requise','non-qualifie'):
            with self.subTest(statut=statut):
                contenu={} if statut is None else {'qualification_amendement_20261011':statut}
                with patch.object(Path,'read_text',return_value=json.dumps(contenu)):
                    with self.assertRaisesRegex(ValueError,'promotion bloquée'):
                        stage.descriptor()



class BundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'document').write_text('Source synthétique, aucune donnée réelle.')
        self.sha=hashlib.sha256((self.root/'document').read_bytes()).hexdigest()
        self.suite={'entrees':{'vps':['document']}}
        self.receipt={'format':1,'confiance':'locale-non-attestee','autorise_publication':False,
                      'resultat':'succes','codes':[0],'identite':{
                       'definition':hashlib.sha256(json.dumps(self.suite,sort_keys=True).encode()).hexdigest(),
                       'entrees':{'vps/document':self.sha}}}
        self.cert={'format':2,'activation':False,'revision':'c'*40,'revision_construction':'a'*40,
            'origine_preuves':'codex-local-non-attestee',
            'manifest':{'sources':{'vps':{}},'toolchain':{'production':{'nixpkgs':preparer.NIXPKGS}}},
            'fichiers':{},'recus_locaux_sha256':{},'qualification':{
             'source_revision':'a'*40,'sorties_nix':{'metier':'/nix/store/'+'a'*32+'-mrjam-metier-'+'a'*12},
             'artefact_sha256':'b'*64,'sources_lisp_sha256':{'vps/document':self.sha}}}
        (self.root/'vps/assemblage').mkdir(parents=True)
        (self.root/'vps/document').write_bytes((self.root/'document').read_bytes())
        (self.root/'recus').mkdir()
        self.actualiser()

    def actualiser(self):
        (self.root/'vps/assemblage/manifest.json').write_text(json.dumps(self.cert['manifest']))
        p=self.root/'recus/fixture.json';p.write_text(json.dumps(self.receipt))
        self.cert['recus_locaux_sha256']={'fixture':preparer.sha(p)}
        self.cert['fichiers']={str(p.relative_to(self.root)):preparer.sha(p)
                               for p in self.root.rglob('*') if p.is_file() and p.name!='stage.json'}

    def verifier(self):
        (self.root/'stage.json').write_text(json.dumps(self.cert))
        original=preparer.sha
        def sha(p):
            return 'b'*64 if str(p).startswith('/nix/store/') else original(p)
        with patch.object(preparer,'sha',side_effect=sha), patch.object(assemblage,'catalogue',return_value={'fixture':self.suite}), patch.object(assemblage,'compilation_entrees',return_value={'vps/document':self.sha}):
            return preparer.verifier_bundle(self.root)

    def test_bundle_exact_operateurs_sans_reconstruction(self):self.assertEqual(self.verifier()['revision'],'c'*40)

    def style_verrouille(self,format_empreintes='sha256'):
        # La révision consommée diffère de la tête Style de l'assemblage.
        self.suite['style_consomme_par']='vision'
        self.suite['entrees']['style']=['src/Style.elm']
        self.cert['manifest']['sources'].update({'vision':{},'style':{}})
        courant=self.root/'style/src/Style.elm';courant.parent.mkdir(parents=True)
        courant.write_text('Source nouvelle, non consommée.')
        consomme=self.root/'styles-consommes/vision/src/Style.elm';consomme.parent.mkdir(parents=True)
        consomme.write_text('Source verrouillée effectivement qualifiée.')
        empreinte=preparer.sha(consomme)
        verrou=self.root/'vision/style.lock.json';verrou.parent.mkdir()
        contenu=consomme.read_bytes()
        verrou_empreinte=(hashlib.sha1(b'blob '+str(len(contenu)).encode()+b'\0'+contenu).hexdigest()
                         if format_empreintes=='git-blob-sha1' else empreinte)
        verrou.write_text(json.dumps({'revision':'b'*40,'fichiers':{'src/Style.elm':verrou_empreinte}}))
        self.cert['manifest']['frontends']={'vision':{'revision_style':'b'*40,
            'verrou_style':'style.lock.json','sha256':preparer.sha(verrou),
            'format_empreintes':format_empreintes}}
        self.cert['styles_consommes']={'vision':{'revision':'b'*40}}
        self.receipt['identite']['entrees']['style/src/Style.elm']=empreinte
        self.receipt['identite']['definition']=hashlib.sha256(json.dumps(self.suite,sort_keys=True).encode()).hexdigest()
        self.actualiser()
        return consomme

    def test_style_reellement_consomme_et_non_sa_tete(self):
        self.style_verrouille()
        self.assertEqual(self.verifier()['revision'],'c'*40)

    def test_verrou_git_blob_historique_et_recu_sha256(self):
        source=self.style_verrouille('git-blob-sha1')
        self.assertEqual(self.receipt['identite']['entrees']['style/src/Style.elm'],preparer.sha(source))
        self.assertEqual(self.verifier()['revision'],'c'*40)

    def test_verrou_git_blob_altere_refuse_meme_si_enveloppe_recalculee(self):
        self.style_verrouille('git-blob-sha1').write_text('Autre source, qualification invalide.')
        self.actualiser()
        with self.assertRaisesRegex(ValueError,'Source Style différente'):self.verifier()

    def test_verrou_git_blob_sans_format_declare_refuse(self):
        self.style_verrouille('git-blob-sha1')
        self.cert['manifest']['frontends']['vision'].pop('format_empreintes')
        self.actualiser()
        with self.assertRaisesRegex(ValueError,'Source Style différente'):self.verifier()

    def test_format_de_verrou_inconnu_refuse(self):
        self.style_verrouille('inconnu')
        with self.assertRaisesRegex(ValueError,'Format de verrou Style inconnu'):self.verifier()

    def test_style_consomme_altere_meme_si_enveloppe_recalculee(self):
        self.style_verrouille().write_text('Autre source, qualification invalide.')
        self.actualiser()
        with self.assertRaisesRegex(ValueError,'Source Style différente'):self.verifier()

    def test_revision_style_consomme_non_verrouillee(self):
        self.style_verrouille();self.cert['styles_consommes']['vision']['revision']='d'*40
        self.actualiser()
        with self.assertRaisesRegex(ValueError,'Révision Style'):self.verifier()

    def test_graphe_incompatible(self):
        self.cert['qualification']['sources_lisp_sha256']={}
        with self.assertRaisesRegex(ValueError,'Graphe'):self.verifier()

    def test_preuve_non_attestee_ne_devient_pas_ci(self):
        self.receipt['autorise_publication']=True;self.actualiser()
        with self.assertRaisesRegex(ValueError,'Reçu'):self.verifier()

    def test_test_echec_ou_manquant(self):
        self.receipt['codes']=[1];self.actualiser()
        with self.assertRaisesRegex(ValueError,'Reçu'):self.verifier()
        self.receipt['codes']=[0];self.actualiser();self.cert['recus_locaux_sha256']={}
        with self.assertRaisesRegex(ValueError,'Catalogue'):self.verifier()

    def test_definition_ou_entrees_alterees(self):
        self.receipt['identite']['definition']='a'*64;self.actualiser()
        with self.assertRaisesRegex(ValueError,'Entrées'):self.verifier()
        self.receipt['identite']['definition']=hashlib.sha256(json.dumps(self.suite,sort_keys=True).encode()).hexdigest()
        self.receipt['identite']['entrees']={};self.actualiser()
        with self.assertRaisesRegex(ValueError,'Entrées'):self.verifier()

    def test_document_modifie(self):
        (self.root/'document').write_text('Altération')
        with self.assertRaisesRegex(ValueError,'Empreintes'):self.verifier()

    def test_fichier_supplementaire(self):
        (self.root/'inattendu').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError,'Empreintes'):self.verifier()

    def test_lien(self):
        (self.root/'lien').symlink_to('document')
        with self.assertRaisesRegex(ValueError,'régulier'):self.verifier()

    def test_toolchain_ou_binaire_different(self):
        self.cert['manifest']['toolchain']['production']['nixpkgs']='/nixpkgs/inconnu'
        with self.assertRaisesRegex(ValueError,'Toolchain'):self.verifier()
        self.cert['manifest']['toolchain']['production']['nixpkgs']=preparer.NIXPKGS
        self.cert['qualification']['artefact_sha256']='c'*64
        with self.assertRaisesRegex(ValueError,'Binaire'):self.verifier()

    def test_store_ou_revision_incoherent(self):
        self.cert['qualification']['sorties_nix']['metier']='/tmp/faux-artefact'
        with self.assertRaisesRegex(ValueError,'Paquet'):self.verifier()
        self.cert['qualification']['sorties_nix']['metier']='/nix/store/'+'a'*32+'-mrjam-metier-'+'a'*12
        self.cert['qualification']['source_revision']='d'*40
        with self.assertRaisesRegex(ValueError,'Révision'):self.verifier()


class AccesPostgres(unittest.TestCase):
    def setUp(self):
        self.avant={'authentication':'local all postgres peer\nlocal vision vision_identite peer map=mrj_identite\nlocal nextcloud nextcloud peer\n',
                    'identMap':'mrj_identite mrj-auth vision_identite\n'}
        self.apres={'authentication':'local vision vision,vision_administration,vision_cycle,vision_admission,vision_fermeture,vision_entretien peer map=mrjam_metier\nlocal matheval matheval_app peer map=mrjam_metier\n'+self.avant['authentication'],
                    'identMap':self.avant['identMap']+'\n'+'\n'.join('mrjam_metier mrjam-metier '+r for r in ('vision','vision_administration','vision_cycle','vision_admission','vision_fermeture','vision_entretien','matheval_app'))+'\n'}

    def test_ajouts_exacts_et_regles_existantes_preservees(self):
        preparer.verifier_acces_postgresql(self.avant,self.apres)

    def test_autre_service_authentification_proprietaire_ordre_refuses(self):
        for avant,apres in [(self.avant,dict(self.apres,authentication=self.apres['authentication'].replace('local nextcloud nextcloud peer','local nextcloud nextcloud trust'))),
                            (self.avant,dict(self.apres,authentication=self.avant['authentication']+self.apres['authentication'])),
                            (self.avant,dict(self.apres,identMap=self.apres['identMap']+'mrjam_metier mrjam-metier postgres\n')),
                            (self.avant,dict(self.apres,identMap=self.apres['identMap'].replace('mrj_identite mrj-auth vision_identite','mrj_identite mrjam-metier vision_identite')))]:
            with self.subTest(apres=apres):
                with self.assertRaises(ValueError):preparer.verifier_acces_postgresql(avant,apres)


if __name__=='__main__':unittest.main()
