{pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {}}:
pkgs.runCommand "mrjam-validation-dispatch-read-probe" {nativeBuildInputs=[pkgs.makeWrapper];} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${./validation_dispatch.py} "$out/lib/validation_dispatch.py"
  cp ${./source_snapshot.py} "$out/lib/source_snapshot.py"
  cat > "$out/lib/probe.py" <<'PY'
  import http.client,json,os,re,sys
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parent))
  import validation_dispatch as D
  def main():
      assert os.getuid()==0 and os.uname().nodename=='srv1982677'
      token=Path('/var/lib/mrjam-ci-credentials/forgejo-registration-token').read_text().strip()
      def request(method,path,body=None):
          assert method=='GET' and body is None and re.fullmatch(re.escape(D.BASE)+r'/actions/runs(?:\?limit=50&page=[1-9][0-9]{0,2}|/[1-9][0-9]{0,9})',path)
          c=http.client.HTTPConnection('127.0.0.1',3004,timeout=20)
          c.request(method,path,headers={'Host':'forge.mrj.am','Authorization':'token '+token})
          response=c.getresponse();raw=response.read(1048577);c.close()
          assert response.status==200 and len(raw)<=1048576
          return json.loads(raw)
      selected=D.find(request,'04754e2c5e531c37bd06864ed2becb3fc218d20d780d9a8c8e1b045956a5d04d','b02bdf1b5d63dcf0e0610723788a7ca7e384932c')
      assert selected is not None and selected['id']==2 and selected['status']=='success'
      print(json.dumps({'code':'LIVE_VALIDATION_RUN_BINDING_VERIFIED','run':selected,'read_only':True,'new_dispatch':False}))
  try:main()
  except Exception:
      print('{"code":"LIVE_VALIDATION_RUN_PROBE_REFUSED"}');raise SystemExit(2) from None
  PY
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/probe" --add-flags '-I -S' --add-flags "$out/lib/probe.py"
''
