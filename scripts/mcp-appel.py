"""Pont HTTP minimal vers les serveurs officiels locaux, depuis cet agent hébergé.

Aucun serveur/protocole de débogage réimplémenté. Une seule requête à la fois
sur les deux outils ; état MCP local privé, aucune connexion de production.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys
import urllib.request

ETAT=Path(__file__).resolve().parents[1]/'state/outils-mcp'
URLS={'cl-mcp':'http://127.0.0.1:4106/mcp','tron':'http://127.0.0.1:4107/mcp'}

# Chemins distants retenus à cette révision. Un ajout répond à un besoin concret,
# avec cible inspectée et contrôle proportionné ; ceci n'est pas un sandbox.
TRON_DISTANTS=frozenset({'repl_eval','repl_compile','repl_frame_locals',
    'repl_get_restarts','repl_invoke_restart'})
TRON_CONSTATS=frozenset({'repl_status','swank_status','swank_debugger_state'})


def texte(resultat):
    return '\n'.join(c.get('text','') for c in resultat.get('content',[]) if c.get('type')=='text')


def verifier_commande(outil,methode,params):
    if outil=='tron' and methode=='tools/call':
        nom=params.get('name')
        if nom not in TRON_DISTANTS | TRON_CONSTATS | {'repl_connect'}:
            raise ValueError('Commande Tron non admise pour cette image applicative : '+str(nom))
        if nom=='repl_connect':
            args=params.get('arguments',{})
            if args!={'type':'swank','host':'127.0.0.1','port':4105}:
                raise ValueError('Connexion Tron : fournir explicitement Swank, 127.0.0.1 et port 4105')


def verifier_connexion(url,session):
    res,_=envoyer(url,{'jsonrpc':'2.0','id':3,'method':'tools/call',
                     'params':{'name':'repl_status','arguments':{}}},session)
    if not res or 'error' in res:
        raise ValueError('Cible Tron non établie ; aucune opération applicative envoyée')
    statut=' '.join(texte(res.get('result',{})).split())
    if statut!='(CONNECTED T TYPE SWANK HOST 127.0.0.1 PORT 4105)':
        raise ValueError('Tron déconnecté ou cible incertaine ; aucune opération applicative envoyée')


def envoyer(url,message,session=None):
    headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream',
             'MCP-Protocol-Version':'2025-03-26'}
    if session:headers['Mcp-Session-Id']=session
    req=urllib.request.Request(url,json.dumps(message).encode(),headers=headers)
    with urllib.request.urlopen(req,timeout=45) as r:
        body=r.read(1024*1024+1)
        if len(body)>1024*1024:raise ValueError('Réponse outil hors limite')
        if r.headers.get_content_type()=='text/event-stream':
            data=[l[6:] for l in body.decode().splitlines() if l.startswith('data: ')]
            if len(data)!=1:raise ValueError('Réponse SSE non unique')
            body=data[0]
        return (json.loads(body) if body else None),r.headers.get('Mcp-Session-Id')


def requete(outil,methode,params):
    verifier_commande(outil,methode,params)
    ETAT.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (ETAT/'image.lock').open('a') as verrou:
        fcntl.flock(verrou,fcntl.LOCK_EX)
        p=ETAT/(outil+'-session.json')
        session=json.loads(p.read_text()).get('session') if p.exists() else None
        if not p.exists():
            init,session=envoyer(URLS[outil],{'jsonrpc':'2.0','id':1,'method':'initialize','params':{
                'protocolVersion':'2025-03-26','capabilities':{},
                'clientInfo':{'name':'codex-pont-local-mrjam','version':'1'}}})
            if 'error' in init:raise ValueError(init['error'])
            p.write_text(json.dumps({'session':session,'serveur':init['result']['serverInfo']})+'\n')
            os.chmod(p,0o600)
            envoyer(URLS[outil],{'jsonrpc':'2.0','method':'notifications/initialized'},session)
        if outil=='tron' and methode=='tools/call' and params.get('name') in TRON_DISTANTS:
            verifier_connexion(URLS[outil],session)
        result,_=envoyer(URLS[outil],{'jsonrpc':'2.0','id':2,'method':methode,'params':params},session)
        if result is None or 'error' in result:raise ValueError(result)
        return result['result']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('outil',choices=URLS)
    parser.add_argument('nom',help='tools/list ou nom exact d’outil officiel')
    args=parser.parse_args()
    if args.nom=='tools/list':res=requete(args.outil,'tools/list',{})
    else:
        contenu=sys.stdin.read()
        res=requete(args.outil,'tools/call',{'name':args.nom,'arguments':json.loads(contenu or '{}')})
    print(json.dumps(res,ensure_ascii=False,indent=2))
    if res.get('isError') or res.get('error_context'):raise SystemExit(1)
