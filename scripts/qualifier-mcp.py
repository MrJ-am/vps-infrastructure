"""Scénario réel dans l'image de tâche raccordée, sans relancer SBCL ni toucher le métier."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pont_mcp',ROOT/'scripts/mcp-appel.py')
pont=importlib.util.module_from_spec(spec);spec.loader.exec_module(pont)
ETAT=ROOT/'state/outils-mcp'


def texte(res):return '\n'.join(c.get('text','') for c in res.get('content',[]) if c['type']=='text')


def main():
    debut=time.monotonic();trace=[]
    def appel(outil,nom,args=None,*,condition=False):
        r=pont.requete(outil,'tools/call',{'name':nom,'arguments':args or {}})
        trace.append({'outil':outil,'nom':nom,'arguments':args or {},'reponse':r})
        t=texte(r)
        if r.get('isError') or r.get('error_context') or 'approval_required' in t:
            raise ValueError('Outil refusé : '+nom)
        if '(ERROR T' in t and not condition:raise ValueError('Échec : '+nom+' '+t[:300])
        return t
    def cl(code):return appel('cl-mcp','repl-eval',{'code':code,'max_output_length':3000,'include_result_preview':False})
    def tron(code):return appel('tron','repl_eval',{'code':code})
    try:
        r=appel('tron','repl_get_restarts',condition=True)
        if 'NO_DEBUGGER_EVENT' not in r:raise ValueError('Débogage suspendu : ne pas réinitialiser la fixture')
        cl('(assert (null cl-mcp:*use-worker-pool*)) (assert (find-package :mrjam-metier))')
        cl('(asdf:load-asd #p"'+str(ROOT/'tests/outils-mcp/mrjam-outils-qualification.asd')+'")')
        appel('cl-mcp','load-system',{'system':'mrjam-outils-qualification','force':False,'clear_fasls':False})
        # Réinstaller la condition volontaire depuis sa source canonique, puis fixture neuve.
        cl('(load #p"'+str(ROOT/'tests/outils-mcp/scenario.lisp')+'")')
        cl('(mrjam-qualification-mcp:initialiser)')
        info=cl('(setf (aref mrjam-qualification-mcp:*objet* 1) 11) (format nil "QUAL:~D:~A:~D" (sb-posix:getpid) mrjam-qualification-mcp:*session* (aref mrjam-qualification-mcp:*objet* 1))')
        marque=re.search(r'QUAL:\d+:qualification-\d+-\d+:11',info).group()
        pid=int(marque.split(':')[1])
        assert marque in tron('(format nil "QUAL:~D:~A:~D" (sb-posix:getpid) mrjam-qualification-mcp:*session* (aref mrjam-qualification-mcp:*objet* 1))')
        tron('(setf (aref mrjam-qualification-mcp:*objet* 1) 12)')
        assert marque[:-2]+'12' in cl('(format nil "QUAL:~D:~A:~D" (sb-posix:getpid) mrjam-qualification-mcp:*session* (aref mrjam-qualification-mcp:*objet* 1))')
        # Débogage choisi dès cette évaluation ; ne jamais répéter cet appel après erreur.
        suspendu=tron('(mrjam-qualification-mcp:operation)')
        assert 'DEBUG T' in suspendu and 'RECALCULER' in suspendu
        # La pile réelle est fournie par l'événement DEBUG de l'évaluation.
        # repl_backtrace inspecte le worker RPC courant dans cette révision.
        assert 'FRAMES' in suspendu and 'MRJAM-QUALIFICATION-MCP:CALCULER' in suspendu
        assert 'IN-DEBUGGER T' in appel('tron','swank_debugger_state')
        for frame in (0,1):
            locaux=appel('tron','repl_frame_locals',{'frame':frame})
            assert 'NAME BASE' in locaux and 'VALUE 40' in locaux and 'NAME FACTEUR' in locaux and 'VALUE 2' in locaux
        assert ':effets 1 :resultat nil' in cl('(list :effets mrjam-qualification-mcp:*effets* :resultat mrjam-qualification-mcp:*resultat*)')
        assert '(RECALCULER ' in appel('tron','repl_get_restarts')
        correction=ROOT/'tests/outils-mcp/correction.lisp'
        compilation=appel('tron','repl_compile',{'code':correction.read_text(),'filename':str(correction),'package':'CL-USER'})
        assert 'COMPILATION-RESULT' in compilation
        appel('tron','repl_invoke_restart',{'restart_index':0})
        cible=f'REPRISE:{pid}:EFFECTS=1:RESULTAT=42:OBJET=12'
        expression='(format nil "REPRISE:~D:EFFECTS=~D:RESULTAT=~D:OBJET=~D" (sb-posix:getpid) mrjam-qualification-mcp:*effets* mrjam-qualification-mcp:*resultat* (aref mrjam-qualification-mcp:*objet* 1))'
        assert cible in cl(expression) and cible in tron(expression)
        assert 'NO_DEBUGGER_EVENT' in appel('tron','repl_get_restarts',condition=True)
        tests=appel('cl-mcp','run-tests',{'system':'mrjam-outils-qualification','framework':'asdf'})
        # Le parseur générique ASDF amont n'a pas de comptage fiable ; exiger
        # le marqueur émis uniquement après les trois assertions réelles.
        assert 'MRJAM-MCP-ASDF:3-ASSERTIONS-REUSSIES' in tests
        preuves={'format':1,'resultat':'succes','confiance':'locale-non-attestee','autorise_publication':False,
                 'pid_applicatif':pid,'marqueur':marque,'mutation_cl_mcp':11,'mutation_tron':12,
                 'locaux':{'base':40,'facteur':2},'effets_avant_erreur':1,'effets_apres_restart':1,
                 'resultat_calcul':42,'connexion_agent':'functions.exec / pont HTTP local / outils officiels',
                 'enregistrement_natif_catalogue_heberge':False,'duree_s':round(time.monotonic()-debut,4),
                 'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  [ROOT/'scripts/mcp-appel.py',ROOT/'scripts/qualifier-mcp.py',correction,*sorted((ROOT/'assemblage/outils').glob('*.*')),*sorted((ROOT/'tests/outils-mcp').glob('*.*'))] if p.is_file()},
                 'trace_sha256':hashlib.sha256(json.dumps(trace,sort_keys=True).encode()).hexdigest()}
        (ETAT/'qualification.json').write_text(json.dumps(preuves,ensure_ascii=False,indent=2)+'\n')
        print(f'MCP : même PID {pid}, marqueur/objet croisés, locaux40/2, correction compilée, restart42, effet unique ; {preuves["duree_s"]}s.')
    finally:
        (ETAT/'qualification-trace-synthetique.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
