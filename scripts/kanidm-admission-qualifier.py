import os,json,sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from kanidm_admission import qualifier
from kanidm_reel import EchecQualification
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--persistante',action='store_true');a=p.parse_args()
    try: print(json.dumps(qualifier(os.environ['MRJAM_KANIDM'],os.environ['MRJAM_CURL'],persistante=a.persistante)))
    except EchecQualification as e: print(str(e),file=sys.stderr);sys.exit(1)
