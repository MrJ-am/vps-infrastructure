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
