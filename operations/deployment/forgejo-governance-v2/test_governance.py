"""Invented public Git objects and scoped IPC only; no VPS or real credential."""
import base64
from contextlib import contextmanager
import copy
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/"forgejo"))
import reconcile
import core as m
import credentials

GIT="/etc/profiles/per-user/jam/bin/git"
TOKEN="a"*40


def document():
    return {"schema_version":1,"owner":"MrJ-am","forgejo_version":"17.0.1","rules_revision":"1"*40,
        "controller_revision":"2"*40,"metadata_disposition":"existing-forgejo-preserved-github-lfs-and-collaboration-retained",
        "repositories":{name:{"source":"reviewed-bundle","bundle":str(m.STAGING/(name+".bundle")),
                              "bundle_sha256":"a"*64,"refs_sha256":"b"*64,"main":"1"*40}
                        for name in m.NAMES}}


def bind(value):
    raw=json.dumps(value,sort_keys=True).encode()
    return m.Binding(raw,hashlib.sha256(raw).hexdigest())


class PlanTests(unittest.TestCase):
    def test_binding_is_complete_exact_and_rejects_synthetic_authority(self):
        binding=bind(document())
        self.assertEqual(binding.policy("protect-main")["rules_revision"],"1"*40)
        for change in (lambda v:v.update(extra=True),lambda v:v["repositories"].pop("vision"),
                       lambda v:v.update(schema_version=True),
                       lambda v:v.update(rules_revision="93bd67666a3b4be9657c333931fa25b2359e165b"),
                       lambda v:v["repositories"]["vision"].update(source="arbitrary-url")):
            value=document();change(value)
            with self.assertRaises(m.Refused):bind(value)

    def test_import_preserves_unrelated_refs_and_only_allows_main_fast_forward(self):
        before={"refs/heads/main":"1"*40,"refs/heads/private-history":"2"*40}
        wanted={"refs/heads/main":"3"*40,"refs/heads/github-import/a/source":"4"*40}
        self.assertEqual(m.import_plan(before,wanted,lambda old,new:(old,new)==("1"*40,"3"*40)),wanted)
        for old,new in ((before,wanted),({"refs/tags/stable":"1"*40},{"refs/tags/stable":"2"*40})):
            with self.assertRaisesRegex(m.Refused,"REFERENCE_CONFLICT"):
                m.import_plan(old,new,lambda *_:False)
        self.assertEqual(m.import_plan(before,{"refs/heads/main":"1"*40},lambda *_:False),{})

    def test_archive_names_bind_bundle_and_preserve_original_main_and_tags(self):
        value={"source":"reviewed-bundle","bundle_sha256":"a"*64,"main":"2"*40}
        target=m.target_refs(value,{"refs/heads/main":"1"*40,"refs/heads/topic/nested":"2"*40,"refs/tags/v1":"3"*40})
        self.assertEqual(target["refs/heads/main"],"2"*40)
        self.assertEqual(target["refs/heads/github-import/"+"a"*16+"/main"],"1"*40)
        self.assertEqual(target["refs/tags/github-import/"+"a"*16+"/v1"],"3"*40)

    def test_reference_parser_rejects_options_duplicates_indirection_and_nonascii(self):
        for ref in ("--delete","refs/heads/a..b","refs/heads/a.lock","refs/heads//bad","refs/heads/.hidden"):
            with self.assertRaises(m.Refused):m.parse_refs(("1"*40+"\t"+ref+"\n").encode())
        line=("1"*40+"\trefs/heads/main\n").encode()
        with self.assertRaises(m.Refused):m.parse_refs(line+line)

    def test_async_forgejo_metadata_must_converge_without_identity_drift(self):
        binding=bind(document())
        original={name:{"id":index,"private":True,"empty":True,"default_branch":"main","actions_enabled":False,"protection":None} for index,name in enumerate(m.NAMES,1)}
        ready={name:dict(row,empty=False) for name,row in original.items()}
        calls=[]
        with patch.object(m,"observe_import_metadata",side_effect=list(original.values())+list(ready.values())):
            m.wait_repository_metadata(None,binding,original,sleep=lambda seconds:calls.append(seconds))
        self.assertEqual(calls,[5])
        drift=copy.deepcopy(ready);drift["vision"]["id"]+=100
        with patch.object(m,"observe_import_metadata",side_effect=list(drift.values())),self.assertRaisesRegex(m.Refused,"IDENTITY_CHANGED"):
            m.wait_repository_metadata(None,binding,original,sleep=lambda _:self.fail("waited after replacement"))

    def test_unconverged_metadata_cannot_be_substituted_or_polled_without_bound(self):
        original={name:{"id":index,"private":True,"empty":True,"default_branch":"main","actions_enabled":False,"protection":None} for index,name in enumerate(m.NAMES,1)}
        calls=[]
        with patch.object(m,"observe_import_metadata",side_effect=list(original.values())*8) as observe, \
                self.assertRaisesRegex(m.Refused,"SOURCE_METADATA_NOT_CONVERGED"):
            m.wait_repository_metadata(None,bind(document()),original,sleep=lambda seconds:calls.append(seconds))
        self.assertEqual(observe.call_count,8*len(m.NAMES));self.assertEqual(calls,[5]*7)

    def test_prewrite_retry_accepts_only_empty_to_nonempty_and_never_visibility_drift(self):
        binding=bind(document())
        rows={name:{"id":index,"private":True,"empty":True,"default_branch":"main","actions_enabled":False,"protection":None} for index,name in enumerate(m.NAMES,1)}
        before={"repositories":rows}
        for changed_visibility in (False,True):
            after=copy.deepcopy(before);after["repositories"]["vision"]["empty"]=False
            if changed_visibility:after["repositories"]["vision"]["private"]=False
            api=SimpleNamespace(token=TOKEN)
            with patch.object(reconcile,"observe",side_effect=[before,after]), \
                    patch.object(reconcile,"plan",return_value={}), \
                    patch.object(reconcile,"Transport",return_value=api), \
                    patch.object(reconcile,"apply",side_effect=[reconcile.Refused("STALE_OR_CHANGED_PLAN"),{"unchanged":True}]) as apply:
                if changed_visibility:
                    with self.assertRaisesRegex(m.Refused,"RECONCILIATION_DRIFT_REFUSED"):
                        m.reconcile_phase(api,binding,"bootstrap-repositories",set())
                    self.assertEqual(apply.call_count,1)
                else:
                    self.assertEqual(m.reconcile_phase(api,binding,"bootstrap-repositories",set()),{"unchanged":True})
                    self.assertEqual(apply.call_count,2)


class DefaultBranchTests(unittest.TestCase):
    def setup_case(self):
        self.binding=bind(document());self.name="Signature"
        self.original={name:{"id":index,"private":True,"empty":True,"default_branch":"main",
                             "actions_enabled":False,"protection":None} for index,name in enumerate(m.NAMES,1)}
        self.observed={name:dict(row,empty=False) for name,row in self.original.items()}
        self.archive="github-import/"+"a"*16+"/main"
        self.observed[self.name]["default_branch"]=self.archive
        refs={"refs/heads/main":"1"*40,"refs/heads/"+self.archive:"2"*40}
        self.imports={name:{"before":{},"after":copy.deepcopy(refs)} for name in m.NAMES}
        self.actual=copy.deepcopy(self.observed);self.requests=[]
        def request(method,path,payload=None,**kwargs):
            self.requests.append((method,path,payload))
            self.assertEqual((method,path,payload),("PATCH",reconcile.path_for(self.name),{"default_branch":"main"}))
            self.actual[self.name]["default_branch"]="main"
        self.api=SimpleNamespace(request=request)
        self.git=SimpleNamespace(remote_refs=lambda name:copy.deepcopy(self.imports[name]["after"]))

    def invoke(self):
        with patch.object(m,"observe_import_metadata",side_effect=lambda api,name:copy.deepcopy(self.actual[name])), \
             patch.object(credentials,"broker",side_effect=lambda *_:contextmanager(lambda:(yield))()):
            m.adopt_empty_default_branches(self.api,self.binding,self.git,TOKEN,self.original,self.observed,self.imports)

    def test_only_initially_empty_exact_import_adopts_literal_main(self):
        self.setup_case();before=copy.deepcopy(self.imports);self.invoke()
        self.assertEqual(self.requests,[("PATCH",reconcile.path_for(self.name),{"default_branch":"main"})])
        self.assertEqual(before,self.imports)
        self.assertEqual(self.actual[self.name],dict(self.observed[self.name],default_branch="main"))

    def test_already_main_is_noop_even_for_existing_nonempty_history(self):
        self.setup_case();self.observed[self.name]["default_branch"]="main"
        self.original[self.name]["empty"]=False
        self.invoke();self.assertEqual(self.requests,[])

    def test_refuses_existing_or_unrelated_default_without_writes(self):
        changes=[lambda:self.original[self.name].update(empty=False),
                 lambda:self.original[self.name].update(protection={"retained":True}),
                 lambda:self.original[self.name].update(actions_enabled=True),
                 lambda:self.imports[self.name]["before"].update({"refs/heads/retained":"2"*40}),
                 lambda:self.observed[self.name].update(default_branch="unrelated"),
                 lambda:self.observed[self.name].update(default_branch="github-import/"+"b"*16+"/main"),
                 lambda:self.observed[self.name].update(id=999),
                 lambda:self.observed[self.name].update(private=False),
                 lambda:self.imports[self.name]["after"].update({"refs/heads/main":"3"*40})]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.setup_case();change()
                with self.assertRaisesRegex(m.Refused,"DEFAULT_BRANCH_ADOPTION_REQUIRED"):self.invoke()
                self.assertEqual(self.requests,[])

    def test_fresh_metadata_or_git_drift_refuses_before_patch(self):
        self.setup_case();self.actual[self.name]["id"]=99
        with self.assertRaisesRegex(m.Refused,"REFERENCE_OBSERVATION_CHANGED"):self.invoke()
        self.assertEqual(self.requests,[])
        self.setup_case();self.git.remote_refs=lambda name:{"refs/heads/main":"4"*40}
        with self.assertRaisesRegex(m.Refused,"REFERENCE_OBSERVATION_CHANGED"):self.invoke()
        self.assertEqual(self.requests,[])

    def test_failed_patch_readback_cannot_be_claimed_success(self):
        self.setup_case();self.api.request=lambda *args,**kwargs:self.requests.append(args)
        with self.assertRaisesRegex(m.Refused,"REFERENCE_READBACK_FAILED"):self.invoke()
        self.assertEqual(len(self.requests),1)

    def test_shared_reconciler_still_refuses_nonmain(self):
        raw={"id":1,"name":"vision","full_name":"MrJ-am/vision","private":True,"archived":False,
             "mirror":False,"empty":False,"has_actions":False,"default_branch":"historical"}
        api=SimpleNamespace(request=lambda *_,**__:raw)
        with self.assertRaisesRegex(reconcile.Refused,"DEFAULT_BRANCH_ADOPTION_REQUIRED"):
            reconcile.observe_repository(api,"vision")


class CredentialTests(unittest.TestCase):
    def request(self,name="vision",host="127.0.0.1:3004"):
        return ("protocol=http\nhost="+host+"\npath=MrJ-am/"+name+".git\nwwwauth[]=Basic realm=\"Gitea\"\n\n").encode()

    def exchange(self,path,request):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.connect(str(path));client.sendall(request);client.shutdown(socket.SHUT_WR)
            return credentials.receive(client)

    def test_broker_is_private_and_only_discloses_to_matching_closed_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);root.chmod(0o700);path=root/"credential.sock"
            with credentials.broker(TOKEN,"vision",socket_path=path,owner=os.getuid()):
                self.assertEqual(path.stat().st_mode&0o777,0o600)
                self.assertIn(TOKEN.encode(),self.exchange(path,self.request()))
                self.assertEqual(self.exchange(path,self.request("matheval")),b"")
                self.assertEqual(self.exchange(path,self.request(host="github.com")),b"")
            self.assertFalse(path.exists())
            self.assertEqual(list(root.iterdir()),[])

    def test_foreign_socket_and_duplicate_fields_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"credential.sock";path.write_text("sentinel")
            with self.assertRaises(ValueError),credentials.broker(TOKEN,"vision",socket_path=path,owner=os.getuid()):pass
            self.assertEqual(path.read_text(),"sentinel")
        with self.assertRaises(ValueError):credentials.read_request(self.request().replace(b"\n\n",b"\nhost=evil\n\n"))


class RealGitTransportTest(unittest.TestCase):
    def test_git_http_adoption_uses_memory_credential_pipe_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/"state";state.mkdir(mode=0o700)
            local=root/"source";destination=root/"http"/"MrJ-am"/"vision.git";destination.parent.mkdir(parents=True)
            env={"HOME":"/nonexistent","GIT_CONFIG_NOSYSTEM":"1","GIT_CONFIG_GLOBAL":"/dev/null","LANG":"C"}
            def git(*args,input=None):
                return subprocess.run([GIT,"-c","user.name=Invented","-c","user.email=invented@example.invalid",*args],
                    input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,check=True).stdout
            git("init","--initial-branch=main",str(local));git("init","--bare","--initial-branch=main",str(destination))
            (local/"README").write_text("invented original source\n");git("-C",str(local),"add","README");git("-C",str(local),"commit","-m","invented original")
            first=git("-C",str(local),"rev-parse","HEAD").strip().decode()
            git("-C",str(local),"push",str(destination),"main:main","main:private-preserved")
            git("-C",str(local),"tag","v1")
            (local/"README").write_text("invented candidate source\n");git("-C",str(local),"commit","-am","invented candidate")
            second=git("-C",str(local),"rev-parse","HEAD").strip().decode()
            bundle=root/"source.bundle";git("-C",str(local),"bundle","create",str(bundle),"--branches","--tags")
            git("--git-dir="+str(destination),"config","http.receivepack","true")
            refs={"refs/heads/main":second,"refs/tags/v1":first}
            source={"source":"reviewed-bundle","bundle":str(bundle),"bundle_sha256":hashlib.sha256(bundle.read_bytes()).hexdigest(),
                    "main":second,"refs_sha256":hashlib.sha256(reconcile.canonical(refs)).hexdigest()}
            credential_socket=state/"credential.sock"
            entry=root/"git-credential"
            entry.write_text("#!"+sys.executable+"\nimport sys\nfrom pathlib import Path\nsys.path.insert(0,"+repr(str(HERE))+")\nimport credentials\nraise SystemExit(credentials.helper(socket_path=Path("+repr(str(credential_socket))+"),owner="+str(os.getuid())+"))\n")
            entry.chmod(0o700)
            backend=Path(git("--exec-path").decode().strip())/"git-http-backend"
            authorization="Basic "+base64.b64encode((credentials.ACCOUNT+":"+TOKEN).encode()).decode()
            class Handler(http.server.BaseHTTPRequestHandler):
                def log_message(self,*_):pass
                def request(self):
                    if self.headers.get("Authorization")!=authorization:
                        self.send_response(401);self.send_header("WWW-Authenticate",'Basic realm="Gitea"');self.end_headers();return
                    url=urlsplit(self.path)
                    body=self.rfile.read(int(self.headers.get("Content-Length","0")))
                    result=subprocess.run([str(backend)],input=body,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                        env={**env,"GIT_PROJECT_ROOT":str(root/"http"),"GIT_HTTP_EXPORT_ALL":"1","REQUEST_METHOD":self.command,
                             "PATH_INFO":url.path,"QUERY_STRING":url.query,"CONTENT_TYPE":self.headers.get("Content-Type",""),
                             "CONTENT_LENGTH":str(len(body)),"REMOTE_USER":credentials.ACCOUNT,"SERVER_PROTOCOL":"HTTP/1.1"},check=True)
                    headers,body=result.stdout.split(b"\r\n\r\n",1)
                    self.send_response(200)
                    for line in headers.decode().splitlines():
                        key,value=line.split(":",1)
                        if key.lower()!="status":self.send_header(key,value.strip())
                    self.end_headers();self.wfile.write(body)
                do_GET=request;do_POST=request
            server=http.server.HTTPServer(("127.0.0.1",3004),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            real_broker=credentials.broker
            try:
                with patch.object(m,"STATE",state),patch.object(credentials,"broker",side_effect=lambda token,name:
                        real_broker(token,name,socket_path=credential_socket,owner=os.getuid())):
                    def invented_run(argv,**kwargs):
                        kwargs["stderr"]=subprocess.PIPE
                        result=subprocess.run(argv,**kwargs)
                        if result.returncode not in (0,1):
                            self.fail("invented Git fixture: "+result.stderr.decode(errors="replace").replace(TOKEN,"<invented-token>")[-1000:])
                        return result
                    instance=m.Git(GIT,str(entry),run=invented_run);instance.adopt("vision",source,TOKEN)
                    instance.adopt("vision",source,TOKEN)
                self.assertEqual(git("--git-dir="+str(destination),"rev-parse","refs/heads/main").strip().decode(),second)
                self.assertEqual(git("--git-dir="+str(destination),"rev-parse","refs/heads/private-preserved").strip().decode(),first)
                self.assertEqual(git("--git-dir="+str(destination),"rev-parse","refs/tags/github-import/"+source["bundle_sha256"][:16]+"/v1").strip().decode(),first)
                self.assertEqual(list(state.iterdir()),[])
            finally:
                server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=="__main__":unittest.main()
