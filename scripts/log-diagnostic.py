"""Sondes Log fermées : phases, erreurs classées et empreintes, aucune valeur privée."""
import importlib.util,json,os,re,sys,subprocess,ast
from pathlib import Path

def classifier(texte,ancien):
    r=ancien.erreur_nix(texte)
    r['attributs_absents']=[a for a in ('version','outPath','enable','paquet','text','users','services')
        if re.search(r'attribute [\'`"]'+a+r'[\'`"] missing',texte)]
    r['conversions']=[t for t in ('string','set','path','function','list')
        if re.search(r'(?:expected|is not|cannot coerce|cannot be coerced).*\b'+t+r'\b',texte)]
    r['options_kanidm']=sorted(set(re.findall(r'(?:services\.kanidm|infrastructure\.log)\.[A-Za-z0-9_.]+',texte)))
    # En-têtes d'options uniquement ; jamais les lignes Definition values.
    options=re.findall(r'The option [`\']([^`\']+)[`\']',texte)
    r['options']=sorted(set(o for o in options if re.fullmatch(
        r'(?:services|infrastructure|systemd|security|boot|users|environment|networking)\.[A-Za-z0-9_."/ =~-]{1,280}',o)))
    return r

def raison_statique(texte,source):
    # Seuls les messages littéraux d'exiger du code scellé. Aucune valeur
    # d'exception libre, identifiant, requête, credential ou ligne métier.
    a=ast.parse(source.read_text());messages={n.args[1].value for n in ast.walk(a)
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='exiger'
        and len(n.args)>1 and isinstance(n.args[1],ast.Constant) and isinstance(n.args[1].value,str)}
    dernier=texte.rstrip().splitlines()[-1] if texte.strip() else ''
    valeur=dernier.removeprefix('ValueError: ')
    return valeur if dernier.startswith('ValueError: ') and valeur in messages else None

def main(revision):
    if os.geteuid()!=0 or not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Cible refusée')
    d=Path('/root/mrjam-assemblages')/revision
    spec=importlib.util.spec_from_file_location('diagnostic_existant',d/'payload/vps/scripts/monolithe-diagnostic.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    f=d/'erreur-commande-privee.log'
    out={'revision':revision,'generation':str(Path('/run/current-system').resolve()),
        'generation_demarrage':str(Path('/nix/var/nix/profiles/system').resolve()),
        'preparation':(d/'preparation-log.json').is_file(),'activation_engagee':(d/'activation-log-privee.json').is_file(),
        'erreur_nix':classifier(f.read_text(),m) if f.is_file() else {}}
    for nom in ('preparation','operation'):
        f=d/('erreur-log-'+nom+'-privee.log')
        if f.is_file():
            texte=f.read_text();out['erreur_'+nom]=m.diagnostic_erreur(texte)
            if nom=='operation':out['erreur_'+nom]['regle']=raison_statique(texte,d/'payload/vps/scripts/log-activer.py')
            cmd=re.search(r'RuntimeError: Commande refusée : (nix-instantiate|nix-build|systemctl|switch-to-configuration), code ([0-9]+)',texte)
            if cmd:out['erreur_'+nom]['commande']={'outil':cmd[1],'code':int(cmd[2])}
    f=d/'erreur-restauration-privee.log'
    if f.is_file():
        inventaire=json.loads((d/'payload/vps/assemblage/tables-privees.json').read_text())
        tables=set(inventaire['vision'])|set(inventaire['matheval'])
        roles=set().union(*(set(t['droits_directs']) for b in ('vision','matheval') for t in inventaire[b].values()))
        out['erreur_restauration']=m.diagnostic_erreur(f.read_text(),tables,roles)
    out['restauration']=(d/'restauration.json').is_file()
    out['retour_enregistre']=(d/'retour-log.json').is_file()
    if out['retour_enregistre']:out['retour']=json.loads((d/'retour-log.json').read_text())
    out['services']={}
    for nom in ('mrjam-metier','kanidm','keycloak','mrj-auth','nginx','postgresql'):
        v=subprocess.run(['systemctl','show',nom,'-p','ActiveState','--value'],capture_output=True,text=True,timeout=10).stdout.strip()
        out['services'][nom]=v if v in ('active','inactive','failed','activating','deactivating') else 'inconnu'
    # Journaux historiques bornés, classification uniquement. Ne publier
    # aucun message libre pouvant contenir une valeur privée.
    journal=subprocess.run(['journalctl','-u','mrjam-metier','-u','kanidm','-u','nginx',
        '--since','30 minutes ago','--no-pager','-o','cat','-n','200'],capture_output=True,text=True,timeout=20).stdout
    absent=sorted(set(re.findall(r'Configuration absente : ([A-Z][A-Z0-9_]{1,80})',journal)))
    out['configuration_absente']=absent
    out['erreurs_runtime']=[v for k,v in {
        'cannot open shared object':'dso_absente','undefined symbol':'symbole_dso',
        'FATAL:':'postgres_fatal','failed to load':'chargement_refuse','Failed to start':'service_demarrage_refuse',
        'duplicate location':'nginx_location_dupliquee','invalid number of arguments':'nginx_arguments',
        'permission denied':'permission_refusee','No such file or directory':'fichier_absent',
        'Configuration métier invalide':'configuration_metier_invalide'}.items() if k.lower() in journal.lower()]
    texte_erreur=(d/'erreur-commande-privee.log').read_text() if (d/'erreur-commande-privee.log').is_file() else ''
    out['unites_echec']=[nom for nom in ('mrjam-metier','kanidm','nginx','postgresql','mrj-auth','keycloak')
        if any(nom+'.service' in l and any(mot in l.lower() for mot in ('failed','failure','refus','error'))
               for l in (texte_erreur+'\n'+journal).splitlines())]
    f=d/'evaluation-log-privee.json'
    if f.is_file():
        r=json.loads(f.read_text());out['services_preserves']=m.differences(r['protegeAvant'],r['protegeApres'])
        binaries=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+/bin/nginx',r['nginx'])
        configs=re.findall(r'/nix/store/[a-z0-9]{32}-[^/\s"\']+\.conf',r['nginx'])
        if len(binaries)==len(configs)==1:
            test=subprocess.run([binaries[0],'-t','-c',configs[0]],capture_output=True,text=True,timeout=20)
            texte=test.stderr
            out['nginx_candidat_code']=test.returncode
            out['nginx_directives_dupliquees']=[v for v in ('proxy_ssl_server_name','proxy_ssl_name','proxy_ssl_verify',
                'client_max_body_size','access_log','proxy_pass','proxy_http_version','proxy_set_header')
                if re.search(re.escape('"'+v+'"')+r'.*duplicate',texte)]
            out['nginx_erreur_categories']=[v for k,v in {'unknown directive':'directive_inconnue',
                'duplicate':'directive_dupliquee','invalid':'invalide','permission denied':'permission_refusee',
                'cannot load certificate':'certificat_indisponible','bind()':'port_indisponible'}.items()
                if k in texte.lower()]
    elif not out['activation_engagee']:
        # Même expression fermée du préparateur, en lecture seule, trace
        # conservée privée ; seuls positions/classes/champs sont publiés.
        cert=json.loads((d/'payload/stage.json').read_text());base=d/'payload/vps/scripts'
        spec=importlib.util.spec_from_file_location('stage_diag_log',base/'monolithe-preparer.py')
        stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(stage)
        bank=json.loads((d/'payload/matheval/research/bank.json').read_text())
        params=dict(configuration=str(Path('/etc/nixos/configuration.nix').resolve()),
            paquet=cert['qualification']['sorties_nix']['metier'],
            documentVision='/srv/mrjam-assemblages/'+revision+'/vision',
            ressourcesMatheval='/srv/mrjam-assemblages/'+revision+'/matheval',
            bankVersion=bank['version'],kanidm=cert['qualification']['sorties_nix']['kanidm'])
        expr='(import '+str(base/'log-evaluation.nix')+' {'+''.join(k+'='+json.dumps(v)+';' for k,v in params.items())+'}).rapport'
        f=d/'diagnostic-nix-trace-privee.log'
        if f.is_file():
            out['trace_nix']=classifier(f.read_text(),m)
        else:
            r=subprocess.run(['nix-instantiate','-I','nixpkgs='+stage.NIXPKGS,'--eval','--strict','--show-trace','--json','--expr',expr],
                capture_output=True,text=True,timeout=90)
            f.write_text(r.stderr);f.chmod(0o600)
            out['trace_nix']=classifier(r.stderr,m)
            out['evaluation_code']=r.returncode
    print(json.dumps(out,ensure_ascii=False))

if __name__=='__main__':main(sys.argv[1])
