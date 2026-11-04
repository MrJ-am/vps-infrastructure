{ pkgs ? import /nix/store/vin7xkmskj4k065z1w7bwwwwp4dbfv93-source {} }:
let discovery=import ./github-proposals.nix {inherit pkgs;};
in pkgs.runCommand "mrjam-source-fetch-live-qualification-1" {
  nativeBuildInputs=[pkgs.makeWrapper];
} ''
  mkdir -p "$out/lib" "$out/bin"
  cp ${discovery}/lib/github_app_auth.py ${discovery}/lib/github_proposals.py "$out/lib/"
  cp ${./source_snapshot.py} "$out/lib/source_snapshot.py"
  cp ${./source_fetch.py} "$out/lib/source_fetch.py"
  cat > "$out/lib/qualify.py" <<'PY'
  import json,os,sys,tempfile
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parent))
  import source_fetch as F
  def main():
      fd=os.open(Path(os.environ['CREDENTIALS_DIRECTORY'])/'github-app',os.O_RDONLY|os.O_NOFOLLOW)
      with os.fdopen(fd,'rb') as stream:
          F.P.credential_metadata(os.fstat(stream.fileno()),os.getuid(),os.getgid())
          credentials=F.P.A.checked(json.loads(stream.read(32769)))
      proposal={'repository':'mrjam-plateforme','repository_id':1437120781,'number':2,
                'draft':False,'branch':'spectre/source-alignment-20261103',
                'base':'6009020151cdd6e069aed67b4970b3b6de1b5151',
                'head':'5a05461e9e3eb7cf77e99b85ae8d49630f13004d'}
      with tempfile.TemporaryDirectory(prefix='mrjam-source-',dir='/tmp') as directory:
          reader=F.receive(directory,'${pkgs.git}/bin/git',proposal,credentials)
          tree=F.S.complete_tree(reader,proposal['head'])
          F.S.require(tree['sha']=='898e81ba8da198cbb6512a64fa54e950ecd24d4b','TREE_BINDING_REFUSED')
          selected=F.S.select_blobs(reader,tree,lambda p:p in {'Cargo.toml','crates/identity/src/tests.rs'})
          F.S.require(len(selected)==2,'SOURCE_SELECTION_REFUSED')
          print(json.dumps({'code':'EXACT_PRIVATE_GITHUB_SOURCE_RECEIVED','repository':proposal['repository'],
                            'number':2,'head':proposal['head'],'tree':tree['sha'],
                            'tree_entries':len(tree['tree']),'selected_blobs_verified':2,
                            'read_token_revoked':True,'candidate_code_executed':False,
                            'deployment_authorized':False,'uid':os.getuid()},sort_keys=True))
  try:main()
  except Exception as error:
      code=str(error) if isinstance(error,(F.S.Refused,F.P.A.Refused)) else 'SOURCE_QUALIFICATION_FAILED'
      print(json.dumps({'code':code,'exception_type':type(error).__name__}))
      raise SystemExit(1) from None
  PY
  makeWrapper ${pkgs.python3}/bin/python3 "$out/bin/qualify-source-fetch" \
    --add-flags "-I -S $out/lib/qualify.py"
''
