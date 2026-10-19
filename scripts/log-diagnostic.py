"""Sondes Log fermées : phases, erreurs classées et empreintes, aucune valeur privée."""
import importlib.util,json,os,re,sys,subprocess,ast,shutil,pwd,hashlib,time
import sqlite3
from pathlib import Path

def inventaire_clients_mcp(actuel, historique):
    """Configurations publiques de clients seulement, aucune session/credential.

    Lecture SQLite mode=ro. Ne publier ni identifiant client, ni nom libre,
    ni redirection : seules tailles et intersections de registres.
    """
    def ids(path, table):
        if not path.is_file():return set()
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=3) as db:
            if not db.execute('SELECT 1 FROM sqlite_master WHERE type=\'table\' AND name=?',(table,)).fetchone():return set()
            return {row[0] for row in db.execute('SELECT id FROM '+table)}
    nouveaux=ids(actuel,'log_oauth_clients');anciens=ids(historique,'oauth_clients')
    return {'clients_actuels':len(nouveaux),'clients_historiques':len(anciens),
            'identifiants_communs':len(nouveaux & anciens)}

def inventaire_reconnexion_mcp(chemin, maintenant):
    """Compter les étapes OAuth sans lire jetons, cookies, sujets ou redirections."""
    if not chemin.is_file():return {'present':False}
    with sqlite3.connect(chemin.as_uri()+'?mode=ro',uri=True,timeout=3) as db:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        tables={r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type=\'table\'')}
        attendues={'log_sessions','log_oauth_requests','log_oauth_codes','log_oauth_tokens'}
        if not attendues.issubset(tables):return {'present':True,'schema_complet':False}
        sessions={}
        for hote in ('vision.mrj.am','audition.mrj.am'):
            row=db.execute('SELECT count(*),coalesce(sum(expires>?),0),max(seen) FROM log_sessions WHERE host=?',
                           (maintenant,hote)).fetchone()
            sessions[hote]={'total':row[0],'non_expirees':row[1],
                            'derniere_lecture_minute':row[2]//60 if row[2] is not None else None}
        out={'present':True,'schema_complet':True,'sessions':sessions}
        for nom,table in (('demandes','log_oauth_requests'),('codes','log_oauth_codes')):
            row=db.execute('SELECT count(*),coalesce(sum(r.expires>?),0),'
                'coalesce(sum(s.digest IS NULL OR s.expires<=?),0),max(r.expires) FROM '+table+
                ' r LEFT JOIN log_sessions s ON s.digest=r.session',(maintenant,maintenant)).fetchone()
            out[nom]={'total':row[0],'non_expires':row[1],'session_absente_ou_expiree':row[2],
                      'derniere_expiration_minute':row[3]//60 if row[3] is not None else None}
        out['jetons']=[]
        for kind in ('access','refresh'):
            row=db.execute('SELECT count(*),coalesce(sum(t.revoked IS NULL AND t.expires>?),0),'
                'coalesce(sum(t.revoked IS NOT NULL),0),'
                'coalesce(sum(s.digest IS NULL OR s.expires<=?),0),max(t.expires) '
                'FROM log_oauth_tokens t LEFT JOIN log_sessions s ON s.digest=t.session WHERE t.kind=?',
                (maintenant,maintenant,kind)).fetchone()
            out['jetons'].append({'type':kind,'total':row[0],'non_expires_non_revoques':row[1],
                'revoques':row[2],'session_absente_ou_expiree':row[3],
                'derniere_expiration_minute':row[4]//60 if row[4] is not None else None})
        return out

def configuration_mcp_actuelle():
    """Comparer le code exécuté et les seules routes/configurations publiques MCP."""
    expr='''let e=import <nixpkgs/nixos/lib/eval-config.nix> { modules=[ /etc/nixos/configuration.nix ]; };
      c=e.config; v=c.services.nginx.virtualHosts."vision.mrj.am".locations; in {
        generation=toString c.system.build.toplevel;
        paquet=toString c.infrastructure.metier.paquet;
        mcp=v."= /mcp".extraConfig;
        refus=v."@vision-mcp-authentication-required".extraConfig;
        verifier=v."= /_vision_mcp_token".proxyPass;
        adresse=c.systemd.services.mrjam-metier.environment.VISION_PUBLIC_MCP_URL or "";
      }'''
    r=subprocess.run(['nix-instantiate','-I','nixpkgs=/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos',
        '--eval','--strict','--json','--expr',expr],capture_output=True,text=True,timeout=90)
    out={'evaluation_reussie':r.returncode==0}
    if r.returncode:return out
    d=json.loads(r.stdout)
    pid=subprocess.run(['systemctl','show','mrjam-metier','-p','MainPID','--value'],
        check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    if not re.fullmatch('[1-9][0-9]*',pid):return dict(out,processus_present=False)
    image=Path('/proc')/pid/'exe';candidat=Path(d['paquet'])/'bin/mrjam-metier'
    def empreinte(p):
        with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
    out.update(generation_configuree=d['generation'],code_actif_sha256=empreinte(image),
        code_configure_sha256=empreinte(candidat),
        controle_mcp_commun='auth_request /_vision_mcp_token;' in d['mcp'],
        defi_bearer='Bearer ' in d['refus'],defi_basic='Basic ' in d['refus'],
        verification_commune=d['verifier']=='http://unix:/run/mrjam-metier/http.sock:/verify-mcp',
        adresse_publique_configuree=d['adresse']=='https://vision.mrj.am/mcp')
    return out

def resume_nginx_mcp(texte):
    """Uniquement des directives techniques connues des locations MCP Vision."""
    out={}
    chemins=('/mcp','/_vision_mcp_token','@vision-mcp-authentication-required')
    for bloc in re.finditer(r'(?ms)^(?P<indent>[ \t]*)location\s+(?:=\s+)?(?P<chemin>\S+)\s*\{\n(?P<corps>.*?)^(?P=indent)\}',texte):
        if bloc['chemin'] not in chemins:continue
        noms=re.findall(r'\bserver_name\s+([^;]+);',texte[:bloc.start()])
        if not noms or 'vision.mrj.am' not in noms[-1].split():continue
        lignes=[]
        for l in bloc['corps'].splitlines():
            if re.match(r'\s*(?:auth_request(?:_set)?|auth_basic|satisfy|error_page|proxy_pass|proxy_set_header\s+(?:X-Mrj-User|X-Mrjam-Service|X-Vision-Authenticated|X-Forwarded-Host))\s',l):
                # Ces directives n'acceptent ici que des noms techniques/chemins,
                # jamais une valeur Authorization/Cookie ni un corps de requête.
                lignes.append(l.strip())
            elif re.match(r'\s*add_header WWW-Authenticate\s',l):
                lignes.append('defi='+('Bearer' if 'Bearer ' in l else 'Basic' if 'Basic ' in l else 'inconnu'))
            elif re.match(r'\s*proxy_set_header Authorization\s',l):
                lignes.append('authorization_transmise='+str(bool(re.fullmatch(
                    r'\s*proxy_set_header Authorization\s+\$http_authorization;\s*',l))))
        out[bloc['chemin']]=lignes
    return out

def nginx_mcp_execute():
    pid=subprocess.run(['systemctl','show','nginx','-p','MainPID','--value'],
        check=True,capture_output=True,text=True,timeout=10).stdout.strip()
    if not re.fullmatch('[1-9][0-9]*',pid):return {'processus_present':False}
    proc=Path('/proc')/pid
    args=proc.joinpath('cmdline').read_bytes().decode().replace('\0',' ')
    match=re.search(r'(?:^|\s)-c\s+(/(?:etc/nginx/|nix/store/)[^\s;]+)',args)
    if not match:return {'configuration_identifiee':False}
    conf=Path(match[1])
    r=subprocess.run([str(proc/'exe'),'-T','-c',str(conf)],capture_output=True,text=True,timeout=20)
    return {'configuration_identifiee':True,'syntaxe_valide':r.returncode==0,
            'configuration_sha256':hashlib.sha256(conf.read_bytes()).hexdigest(),
            'routes':resume_nginx_mcp(r.stdout) if r.returncode==0 else {}}

def resumer_http_mcp(lignes):
    """Chronologie par minute/statut, sans IP, identifiant ni texte libre."""
    groupes={}
    for ligne in lignes:
        try:e=json.loads(ligne)
        except (ValueError,TypeError):continue
        if not isinstance(e,dict) or e.get('site')!='vision.mrj.am' or e.get('route')!='mcp':continue
        date=e.get('date','');methode=e.get('methode');statut=e.get('statut');amont=e.get('amont','')
        if not isinstance(date,str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)',date):continue
        if methode not in ('GET','POST','HEAD','OPTIONS') or type(statut)!=int or not 100<=statut<=599:continue
        if not isinstance(amont,str) or not re.fullmatch(r'(?:-|[1-5][0-9]{2})(?:, (?:-|[1-5][0-9]{2})){0,5}',amont):amont='inconnu'
        cle=(date[:16]+date[19:],methode,statut,amont)
        groupes[cle]=groupes.get(cle,0)+1
    return [dict(minute=k[0],methode=k[1],statut=k[2],amont=k[3],nombre=v) for k,v in sorted(groupes.items())]

def journal_http_mcp():
    r=subprocess.run(['journalctl','--namespace=http','-t','http_acces','--since','90 minutes ago',
        '--no-pager','-o','cat','-n','5000'],capture_output=True,text=True,timeout=20)
    return {'lecture_reussie':r.returncode==0,'limite':5000,'chronologie':resumer_http_mcp(r.stdout.splitlines())}

def resumer_rpc_mcp(lignes):
    """Résultats JSON-RPC agrégés, sans corps, outil ni identifiant de trace."""
    groupes={}
    for ligne in lignes:
        try:e=json.loads(ligne)
        except (ValueError,TypeError):continue
        if not isinstance(e,dict):continue
        message=e.get('MESSAGE','');date=e.get('__REALTIME_TIMESTAMP','')
        if not isinstance(message,str) or not isinstance(date,str) or not re.fullmatch('[0-9]{1,18}',date):continue
        m=re.fullmatch(r'mcp_trace=[0-9]+ (?:method=(initialize|ping|tools/list|tools/call|autre) tool=[a-z_]{1,80} result=(ok|tool_error|-?[0-9]{1,10})|result=(parse_error|invalid_request))',message)
        if not m:continue
        cle=(int(date)//60000000,m[1] or 'inconnue',m[2] or m[3])
        groupes[cle]=groupes.get(cle,0)+1
    return [dict(minute_utc=k[0],methode=k[1],resultat=k[2],nombre=v) for k,v in sorted(groupes.items())]

def journal_rpc_mcp():
    r=subprocess.run(['journalctl','-u','mrjam-metier','--since','90 minutes ago',
        '--no-pager','-o','json','-n','1000'],capture_output=True,text=True,timeout=20)
    return {'lecture_reussie':r.returncode==0,'limite':1000,'chronologie':resumer_rpc_mcp(r.stdout.splitlines())}

def ecart_generations():
    """Comparer les unités déployées sans publier leur contenu ou leurs secrets."""
    actif=Path('/run/current-system').resolve()
    demarrage=Path('/nix/var/nix/profiles/system').resolve()
    connus={'mrjam-metier.service','kanidm.service','postgresql.service','nginx.service',
        'nginx-config-reload.service','forgejo.service','keycloak.service','mrj-auth.service'}
    def unites(racine):
        p=racine/'etc/systemd/system'
        return {f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in p.glob('*.service') if f.is_file()}
    a=unites(actif);b=unites(demarrage)
    differents={k for k in a.keys()|b.keys() if a.get(k)!=b.get(k)}
    return {'identiques':actif==demarrage,'unites_differentes':sorted(differents & connus),
        'autres_unites_differentes':len(differents-connus)}

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

def statut_http(texte):
    # Code numérique seulement : ni URL, en-tête, corps ni message libre.
    m=re.search(r'^urllib\.error\.HTTPError: HTTP Error ([1-5][0-9]{2}):',texte,re.MULTILINE)
    return int(m[1]) if m else None

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
    # Promotions de présentation : lecture seule, chemins fermés, diagnostics
    # classés sans lignes libres de configuration ni paramètres privés.
    interfaces=Path('/root/mrjam-corrections/log-interface')
    out['interfaces']=[]
    if interfaces.is_dir():
        for item in sorted(interfaces.iterdir()):
            if not re.fullmatch('[a-f0-9]{40}',item.name) or item.is_symlink():continue
            err=item/'erreur-commande-privee.log'
            resume={'revision':item.name,'activation_engagee':(item/'plan.json').is_file(),
                'terminee':(item/'termine.json').is_file(),'retour':(item/'retour.json').is_file(),
                'erreur_nix':classifier(err.read_text(),m) if err.is_file() else {}}
            if err.is_file():
                resume['attributs_absents']=sorted(set(re.findall(r"attribute ['`]([A-Za-z_][A-Za-z0-9_]{0,63})['`] missing",err.read_text())))
            # Les contextes de package Nix peuvent varier entre le checkout
            # local et la configuration installée. Lire seulement type/attributs.
            if not resume['activation_engagee']:
                expr='let c=(import <nixpkgs/nixos/lib/eval-config.nix> { modules=[ /etc/nixos/configuration.nix ]; }); p=c.config.infrastructure.metier.paquet; in { type=builtins.typeOf p; attrs=if builtins.isAttrs p then builtins.attrNames p else []; typeOption=c.options.infrastructure.metier.paquet.type.name; }'
                q=subprocess.run(['nix-instantiate','-I','nixpkgs=/nix/store/81s59zcy998ym4b36ayr29cjc9yhma5n-nixos-26.05.8639.c5c4a43b0e80/nixos','--eval','--strict','--json','--expr',expr],capture_output=True,text=True,timeout=90)
                if q.returncode==0:resume['paquet_actif_metadata']=json.loads(q.stdout)
            out['interfaces'].append(resume)
    for nom in ('preparation','operation'):
        f=d/('erreur-log-'+nom+'-privee.log')
        if f.is_file():
            texte=f.read_text();out['erreur_'+nom]=m.diagnostic_erreur(texte)
            if nom=='operation':
                out['erreur_'+nom]['regle']=raison_statique(texte,d/'payload/vps/scripts/log-activer.py')
                out['erreur_'+nom]['statut_http']=statut_http(texte)
            cmd=re.search(r'RuntimeError: Commande refusée : (nix-instantiate|nix-build|systemctl|switch-to-configuration), code ([0-9]+)',texte)
            if cmd:out['erreur_'+nom]['commande']={'outil':cmd[1],'code':int(cmd[2])}
    f=d/'erreur-restauration-privee.log'
    if f.is_file():
        inventaire=json.loads((d/'payload/vps/assemblage/tables-privees.json').read_text())
        tables=set(inventaire['vision'])|set(inventaire['matheval'])
        roles=set().union(*(set(t['droits_directs']) for b in ('vision','matheval') for t in inventaire[b].values()))
        out['erreur_restauration']=m.diagnostic_erreur(f.read_text(),tables,roles)
    out['restauration']=(d/'restauration.json').is_file()
    out['courriel_engage']=(d/'courriel-log.json').is_file()
    if out['courriel_engage']:
        out['courriel_accepte']=json.loads((d/'courriel-log.json').read_text()).get('accepte_par_relais') is True
    f=d/'sondes-log.json'
    if f.is_file():out['sondes_publiques']=json.loads(f.read_text())
    out['retour_enregistre']=(d/'retour-log.json').is_file()
    if out['retour_enregistre']:out['retour']=json.loads((d/'retour-log.json').read_text())
    out['services']={}
    out['registres_clients_mcp']=inventaire_clients_mcp(
        Path('/var/lib/mrjam-metier/log/sessions.sqlite'),Path('/var/lib/mrj-auth/sessions.sqlite'))
    out['reconnexion_mcp']=inventaire_reconnexion_mcp(Path('/var/lib/mrjam-metier/log/sessions.sqlite'),int(time.time()))
    out['configuration_mcp']=configuration_mcp_actuelle()
    out['nginx_mcp']=nginx_mcp_execute()
    out['http_mcp']=journal_http_mcp()
    out['rpc_mcp']=journal_rpc_mcp()
    out['ecart_generations']=ecart_generations()
    for nom in ('mrjam-metier','kanidm','keycloak','mrj-auth','nginx','postgresql'):
        v=subprocess.run(['systemctl','show',nom,'-p','ActiveState','--value'],capture_output=True,text=True,timeout=10).stdout.strip()
        out['services'][nom]=v if v in ('active','inactive','failed','activating','deactivating') else 'inconnu'
    # Journaux historiques bornés, classification uniquement. Ne publier
    # aucun message libre pouvant contenir une valeur privée.
    journal=subprocess.run(['journalctl','-u','mrjam-metier','-u','kanidm','-u','nginx',
        '--since','30 minutes ago','--no-pager','-o','cat','-n','200'],capture_output=True,text=True,timeout=20).stdout
    absent=sorted(set(re.findall(r'Configuration absente : ([A-Z][A-Z0-9_]{1,80})',journal)))
    out['configuration_absente']=absent
    unites=('nginx.service','nginx-config-reload.service','kanidm.service','mrjam-metier.service',
        'postgresql.service','postgresql-setup.service','systemd-tmpfiles-setup.service','systemd-sysusers.service')
    args=['journalctl','--since','30 minutes ago','--no-pager','-o','json','-n','400']
    for unit in unites:args+=['-u',unit]
    lignes=subprocess.run(args,capture_output=True,text=True,timeout=20).stdout.splitlines()
    evenements=[]
    for ligne in lignes:
        try:e=json.loads(ligne)
        except ValueError:continue
        unit=e.get('UNIT',e.get('_SYSTEMD_UNIT',e.get('OBJECT_SYSTEMD_UNIT')))
        if unit not in unites:continue
        message=e.get('MESSAGE','')
        if not isinstance(message,str):continue
        classes=[v for k,v in {'failed':'echec','permission denied':'permission',
            'no such file':'fichier_absent','connection refused':'connexion_refusee',
            'invalid':'invalide','exit-code':'sortie_erreur','status=':'statut'}.items() if k in message.lower()]
        if classes:evenements.append({'unite':unit,'classes':classes})
    out['incidents_unites_systeme']=evenements[-40:]
    sauvegarde=subprocess.run(['journalctl','-u','mrjam-sauvegarde','--since','60 minutes ago',
        '--no-pager','-o','cat','-n','100'],capture_output=True,text=True,timeout=15).stdout
    out['sauvegarde_erreurs']=[v for k,v in {
        'readonly database':'sqlite_lecture_seule','read-only file system':'systeme_fichiers_lecture_seule',
        'unable to open database':'sqlite_ouverture','database is locked':'sqlite_verrou',
        'permission denied':'permission','connection refused':'connexion_refusee',
        'admin socket':'socket_administratif','peer authentication failed':'postgres_peer',
        'no such file':'fichier_absent','error:':'erreur_commande','failed to':'commande_refusee'
        }.items() if k in sauvegarde.lower()]
    out['sauvegarde_fichiers_concernes']=[nom for nom,path in {
        'anciennes_sessions':'/var/lib/mrj-auth/sessions.sqlite',
        'sessions_log':'/var/lib/mrjam-metier/log/sessions.sqlite',
        'stockage_native':'/var/lib/kanidm','socket_native':'/run/kanidmd/admin.sock',
        'destination':'/var/backup/mrjam'}.items() if path in sauvegarde]
    # Stderr des seules commandes de backup, jamais un corps applicatif.
    # Supprimer paramètres cités, chemins, identifiants et toute ligne portant
    # un vocabulaire de credential avant de publier un diagnostic borné.
    messages=[]
    for ligne in sauvegarde.splitlines():
        if not any(k in ligne.lower() for k in ('no such file','error:','failed to','cannot ')):continue
        if re.search(r'password|token|authorization|cookie|secret|mail|subject',ligne,re.I):continue
        ligne=re.sub(r'"[^"\n]*"|\x27[^\x27\n]*\x27','<parametre>',ligne)
        ligne=re.sub(r'/[^\s,;:)]*','<chemin>',ligne)
        ligne=re.sub(r'[A-Za-z0-9_+=.-]{24,}','<identifiant>',ligne)
        messages.append(ligne[:250])
    out['sauvegarde_messages_commandes']=messages[-8:]
    metier_journal=subprocess.run(['journalctl','-u','mrjam-metier','--since','30 minutes ago',
        '--no-pager','-o','cat','-n','100'],capture_output=True,text=True,timeout=15).stdout
    out['demarrages_metier_refuses']=metier_journal.count('Démarrage métier refusé : configuration ou dépendance indisponible.')
    uid=pwd.getpwnam('mrjam-metier').pw_uid
    out['etat_log_permissions']={}
    for nom in ('sessions.sqlite','sessions.sqlite-wal','sessions.sqlite-shm'):
        f=Path('/var/lib/mrjam-metier/log')/nom
        if f.exists():
            s=f.stat();out['etat_log_permissions'][nom]={'proprietaire_metier':s.st_uid==uid,
                'mode':oct(s.st_mode & 0o777),'octets':s.st_size}
    out['erreurs_runtime']=[v for k,v in {
        'cannot open shared object':'dso_absente','undefined symbol':'symbole_dso',
        'FATAL:':'postgres_fatal','failed to load':'chargement_refuse','Failed to start':'service_demarrage_refuse',
        'duplicate location':'nginx_location_dupliquee','invalid number of arguments':'nginx_arguments',
        'permission denied':'permission_refusee','No such file or directory':'fichier_absent',
        'Configuration métier invalide':'configuration_metier_invalide'}.items() if k.lower() in journal.lower()]
    texte_erreur=(d/'erreur-commande-privee.log').read_text() if (d/'erreur-commande-privee.log').is_file() else ''
    out['activation_systeme_categories']=[v for k,v in {
        'warning: user activation for root failed':'activation_utilisateur_root',
        'Unable to list users with logind:':'inventaire_logind',
        'Failed to run activate script':'script_activation',
        'systemd daemon reload failed':'rechargement_systemd',
        'Failed to restart sysinit-reactivation.target':'reactivation_sysinit',
        'warning: the following units failed:':'unites_echec'}.items() if k in texte_erreur]
    # Noms techniques fixes ou unités de retour portant seulement le hash
    # public de cet assemblage ; aucune valeur personnelle issue des journaux.
    techniques=set(unites)|{'systemd-journald@http.service','systemd-journald@identite.service',
        'sysinit-reactivation.target','dbus.service','dbus-broker.service','user@0.service',
        'user-runtime-dir@0.service','mrjam-log-retour-'+revision[:12]+'.service',
        'mrjam-log-retour-'+revision[:12]+'.timer'}
    out['unites_activation_erreur']=sorted(set(re.findall(
        r'(?:Failed to (?:start|stop|reload|restart) |units failed: )([A-Za-z0-9@_.-]+\.(?:service|target|timer))',
        texte_erreur)) & techniques)
    echecs=re.findall(r'warning: the following units failed: ([^\n]+)',texte_erreur)
    out['unites_signalees_par_activation']=sorted({n.strip() for liste in echecs for n in liste.split(',')
        if re.fullmatch(r'[A-Za-z0-9@_.-]{1,160}\.(?:service|target|timer)',n.strip())})
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
            out['nginx_directives_dupliquees']=sorted(set(re.findall(r'"([a-z][a-z0-9_]{1,60})" directive is duplicate',texte)))
            out['nginx_categories_precises']=[v for v in ('duplicate upstream','duplicate location','already bound',
                'shared memory zone','duplicate directive','directive is duplicate','already declared') if v in texte.lower()]
            out['nginx_upstreams_dupliques']=re.findall(r'duplicate upstream "([a-zA-Z][a-zA-Z0-9_-]{0,80})"',texte)
            out['nginx_locations_dupliquees']=re.findall(r'duplicate location "([=/~^ @A-Za-z0-9_./-]{1,120})"',texte)
            out['nginx_zones']=sorted(set(z for z in ('protected_api_per_ip','mrjam_metier','vision_api','log_auth') if z in texte))
            out['nginx_erreur_categories']=[v for k,v in {'unknown directive':'directive_inconnue',
                'duplicate':'directive_dupliquee','invalid':'invalide','permission denied':'permission_refusee',
                'cannot load certificate':'certificat_indisponible','bind()':'port_indisponible'}.items()
                if k in texte.lower()]
            # Certificat public seulement, sans démarrer le serveur natif ni
            # lire une clé privée. Même CA que le proxy candidat, codes seuls.
            contenu=Path(configs[0]).read_text()
            ca=re.findall(r'proxy_ssl_trusted_certificate\s+(/nix/store/[a-z0-9]{32}-[^;\s]+/etc/ssl/certs/ca-bundle\.crt);',contenu)
            openssl=shutil.which('openssl')
            if not openssl:
                nixpkgs=json.loads((d/'payload/vps/assemblage/manifest.json').read_text())['toolchain']['production']['nixpkgs']
                q=subprocess.run(['nix-instantiate','-I','nixpkgs='+nixpkgs,'--eval','--strict','--json',
                    '--expr','let p=import <nixpkgs> {}; in toString (p.lib.getBin p.openssl)'],
                    capture_output=True,text=True,timeout=20)
                if q.returncode==0:
                    candidat=Path(json.loads(q.stdout))/'bin/openssl'
                    if candidat.is_file():openssl=str(candidat)
            out['verification_chaine_disponible']=bool(openssl and len(set(ca))==1)
            if openssl and len(set(ca))==1:
                cert='/var/lib/acme/log.mrj.am/fullchain.pem'
                out['verification_chaine_proxy']={str(depth):subprocess.run(
                    [openssl,'verify','-verify_hostname','log.mrj.am','-verify_depth',str(depth),
                     '-CAfile',ca[0],'-untrusted',cert,cert],capture_output=True,timeout=10).returncode
                    for depth in (1,2,3)}
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
