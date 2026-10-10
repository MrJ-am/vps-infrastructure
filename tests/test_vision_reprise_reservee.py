"""Preuve exacte exigée et association existante constatée sans modification."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('reservee',ROOT/'scripts/vision-reprise-reservee.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


class Reprise(unittest.TestCase):
    def test_diagnostic_reel_exact_et_complet_necessaire(self):
        r=json.loads((ROOT/'operations/vision-activation-diagnostic-reel.json').read_text())
        m.verifier_diagnostic(r)
        for k,v in [('version',True),('infrastructure','a'*40),('essai','a'*40),
                ('schema',dict(nombre=18,maximum=18)),('retour_effectif',False),
                ('association_initiale_preservee',False),('identite_courante_retablie',False),
                ('inscriptions',True),('activation',True)]:
            d=copy.deepcopy(r);d[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.verifier_diagnostic(d)

    def test_verification_ne_modifie_pas_l_association(self):
        i=dict(issuer='https://log.mrj.am/realms/mrjam',sujet='synthetique')
        h=dict(utilisateur_historique='synthetique')
        r=dict(comptes=1,administrateurs=1,identites=1,issuer=i['issuer'],sujet=i['sujet'],
            utilisateur=h['utilisateur_historique'],actif=True,inscriptions=False)
        requetes=[]
        def sql(q):
            requetes.append(q);return json.dumps(r) if 'json_build_object' in q else 't'
        m.verifier_association(sql,i,h)
        self.assertTrue(all(q.startswith('SELECT ') for q in requetes))
        for k,v in [('comptes',2),('actif',False),('sujet','autre'),('inscriptions',True)]:
            original=r[k];r[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):m.verifier_association(sql,i,h)
            r[k]=original

    def test_preuve_precedente_conservee_apres_test_sans_exiger_generation_ancienne(self):
        spec=importlib.util.spec_from_file_location('prive_reprise',ROOT/'scripts/identite-preparer.py')
        prive=importlib.util.module_from_spec(spec);spec.loader.exec_module(prive)
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'operations').mkdir()
            (d/'operations/vision-activation-diagnostic-reel.json').write_text((ROOT/'operations/vision-activation-diagnostic-reel.json').read_text())
            precedent=d/'precedent';precedent.mkdir()
            for n in ('commence','sql-engage','identite-migree','identite-retablie','retour-termine','echec'):
                p=precedent/n;p.write_text('1\n');p.chmod(0o600)
            p=precedent/'plan.json';p.write_text(json.dumps(dict(infrastructure=m.ESSAI,ancien=str(d/'ancien'))));p.chmod(0o600)
            def chemin(n):
                return {'/root/vision-essais':d,str(d/m.ESSAI):precedent,
                    '/run/current-system':d/'nouveau','/nix/var/nix/profiles/system':d/'ancien'}.get(str(n),Path(n))
            # /root/vision-essais / ESSAI utilise l'opérateur de Path, donc
            # faire correspondre son parent à un dossier fixture du même nom.
            precedent.rename(d/m.ESSAI)
            construction=SimpleNamespace(dossier_prive=lambda p:None)
            with patch.object(m,'Path',side_effect=chemin):
                m.verifier_precedent(d,prive,construction,socle_ancien=False)
                with self.assertRaises(ValueError):m.verifier_precedent(d,prive,construction)


if __name__=='__main__':unittest.main()
