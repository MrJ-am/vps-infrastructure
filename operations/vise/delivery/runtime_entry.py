"""Fixed launcher inside a candidate namespace; synthetic runtime identity only."""
import ctypes,json,os,signal,subprocess,sys,time
from pathlib import Path

def main():
    if len(sys.argv)!=2 or sys.argv[1] not in {'serve','api'}:return 2
    if ctypes.CDLL(None).prctl(4,0,0,0,0)!=0:return 2
    value=json.loads(Path('/support/runtime.json').read_bytes())
    if set(value)!={'password','node'}:return 2
    env=dict(os.environ)
    if sys.argv[1]=='api':
        env.update(CARNET_API_TEST_URL='http://127.0.0.1:3017',CARNET_API_TEST_ORIGIN='https://vise.mrj.am')
        os.execve(value['node'],[value['node'],'--test','/support/api-tests.mjs'],env)
    env.update(CARNET_DB_HOST='127.0.0.1',CARNET_DB_PORT='55432',CARNET_DB_NAME='etp_carnet',
        CARNET_DB_USER='etp_carnet',CARNET_DB_PASSWORD=value['password'],CARNET_SCHEMA_MODE='existing-v1',
        CARNET_PUBLIC_URL='https://vise.mrj.am',CARNET_SECURE_COOKIE='true',
        CARNET_DIST='/support/dist',CARNET_DELETION_LEDGER='/job/deletions.log',CARNET_BIND='127.0.0.1:3017')
    process=subprocess.Popen(['/support/server'],env=env,stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        while process.poll() is None and not Path('/job/stop').exists():time.sleep(0.1)
        if process.poll() is None:process.send_signal(signal.SIGTERM)
        return process.wait(timeout=30)
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:raise SystemExit(2) from None
