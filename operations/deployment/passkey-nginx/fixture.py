"""Invented real Nginx routing and failure/expiration restoration tests."""
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import socketserver
import ssl
import subprocess
import sys
import time
import traceback

ROOT=Path("/etc/synthetic-nginx")
HELPER=Path("/run/synthetic-nginx-helper")
WORK=Path("/run/mrjam-passkey-nginx-route")
DROPIN=Path("/run/systemd/system/nginx.service.d/90-mrjam-passkey-portal.conf")
CONTROL="mrjam-passkey-nginx-route.service"
PREFIX="/_mrjam-worker-provision/"
SOCKET=Path("/run/mrjam-kanidm-passkey-portal/http.sock")


def require(value,label):
    if not value:raise RuntimeError(label)


def command(args,check=True):
    item=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=70)
    if check:require(item.returncode==0,"FIXTURE_COMMAND_FAILED_"+args[0].rsplit("/",1)[-1])
    return item


def manager(*args,check=True):return command(["systemctl",*args],check=check)


def request(path="/",host="log.mrj.am",headers=None):
    context=ssl.create_default_context(cafile=str(ROOT/"certificate.pem"))
    peer=http.client.HTTPSConnection("127.0.0.1",443,context=context,timeout=5)
    peer._context.check_hostname=False
    try:
        peer.request("GET",path,headers={"Host":host,**(headers or {})})
        response=peer.getresponse();raw=response.read(65536)
        require(response.status==200,"FIXTURE_HTTP_STATUS")
        return raw
    finally:peer.close()


def old_routes():
    require(request()==b"OLD-KANIDM-ROUTE","OLD_PRIMARY_CHANGED")
    require(request(host="other.invalid")==b"OTHER-UNMODIFIED","OTHER_HOST_CHANGED")


def ready():
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if WORK.joinpath("ready.json").exists():
            try:
                with socket.create_connection(("127.0.0.1",443),timeout=.2):return
            except OSError:pass
        time.sleep(.1)
    raise RuntimeError("TEMPORARY_ROUTE_NOT_READY")


def restored():
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        if not DROPIN.exists() and not WORK.joinpath("state.json").exists():
            try:old_routes();return
            except OSError:pass
        time.sleep(.1)
    raise RuntimeError("TEMPORARY_ROUTE_NOT_RESTORED")


def stop():
    manager("stop",CONTROL,check=False)
    restored()
    manager("reset-failed",CONTROL,check=False)


def bind():
    raw=manager("show","nginx.service","--property=ExecStart,FragmentPath").stdout.decode()
    executable=re.search(r"path=([^ ;}]+)",raw)[1]
    configuration=re.search(r" -c ([^ ;}]+)",raw)[1]
    fragment=re.search(r"^FragmentPath=(.+)$",raw,re.M)[1]
    spec=importlib.util.spec_from_file_location("probe",ROOT/"preflight_passkey_nginx.py")
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    old=Path(configuration).read_bytes();begin,end=probe.server_position(old)
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    item={"generation":os.path.realpath("/run/current-system"),"configuration":configuration,
          "configuration_sha256":sha(configuration),"executable":executable,"executable_sha256":sha(executable),
          "unit":os.path.realpath(fragment),"unit_sha256":sha(os.path.realpath(fragment)),
          "tls_server_sha256":hashlib.sha256(old[begin:end+1]).hexdigest()}
    HELPER.mkdir(mode=0o700)
    for name in ("route.py","preflight_passkey_nginx.py"):
        shutil.copyfile(ROOT/name,HELPER/name)
        require((HELPER/name).read_bytes()==(ROOT/name).read_bytes(),"SOURCE_COPY_MISMATCH")
    HELPER.joinpath("binding.json").write_text(json.dumps(item))
    return item,old,end


def qualify():
    require(os.geteuid()==0,"SYNTHETIC_ROOT_REQUIRED")
    item,old,end=bind();old_routes();checks=[]
    # Establish a real successful baseline before interpreting negative cases.
    manager("start",CONTROL);ready();stop()
    original=item.copy()
    item["configuration_sha256"]="0"*64
    HELPER.joinpath("binding.json").write_text(json.dumps(item))
    manager("start",CONTROL,check=False);time.sleep(.5);stop()
    require(not DROPIN.exists(),"WRONG_HASH_INSTALLED_OVERRIDE")
    HELPER.joinpath("binding.json").write_text(json.dumps(original))
    checks.append("changed-immutable-config-hash-refused-without-route")

    # An existing active worker has its invented TLS certificate in memory.
    # Removing the test certificate makes real nginx -t refuse before restart.
    certificate=Path("/run/synthetic-nginx/certificate.pem")
    certificate.unlink()
    manager("start",CONTROL,check=False);time.sleep(.5);stop()
    require(not WORK.joinpath("nginx.conf").exists(),"FAILED_SYNTAX_LEFT_CONFIG")
    shutil.copyfile(ROOT/"certificate.pem",certificate)
    checks.append("real-nginx-test-failure-preserves-running-old-configuration")

    Path("/run/synthetic-nginx/refuse-next-start").touch()
    manager("start",CONTROL,check=False)
    deadline=time.monotonic()+10
    while Path("/run/synthetic-nginx/refuse-next-start").exists() and time.monotonic()<deadline:time.sleep(.1)
    restored();stop()
    require(not Path("/run/synthetic-nginx/refuse-next-start").exists(),"RESTART_FAILURE_NOT_REACHED")
    checks.append("failed-restart-automatically-restores-old-nginx")

    manager("start",CONTROL);ready();old_routes()
    spec=importlib.util.spec_from_file_location("route",HELPER/"route.py")
    route=importlib.util.module_from_spec(spec);spec.loader.exec_module(route)
    require(WORK.joinpath("nginx.conf").read_bytes()==old[:end]+route.LOCATION+old[end:],"OTHER_CONFIG_BYTES_CHANGED")
    require(Path(original["configuration"]).read_bytes()==old,"IMMUTABLE_OLD_CONFIG_MODIFIED")
    response=json.loads(request(PREFIX+"portal.js",headers={"Authorization":"INVENTED-STRIP","Cookie":"INVENTED-STRIP","Origin":"https://log.mrj.am"}))
    require(response=={"path":PREFIX+"portal.js","host":"log.mrj.am","authorization":False,"cookie":False,"origin":"https://log.mrj.am"},"PROXY_HEADER_OR_PREFIX_MISMATCH")
    checks.append("one-prefix-proxied-with-host-fixed-cookies-and-authorization-stripped")
    checks.append("all-other-config-bytes-and-existing-vhosts-preserved")

    duplicate=command([sys.executable,"-I","-S",str(HELPER/"route.py"),"apply"],check=False)
    require(duplicate.returncode!=0 and WORK.joinpath("ready.json").exists(),"CONCURRENT_ROUTE_NOT_REFUSED")
    stop();checks.append("concurrent-apply-refused-and-explicit-stop-restores")

    manager("start",CONTROL);ready()
    manager("kill","--kill-whom=main","--signal=KILL",CONTROL)
    restored();stop();checks.append("main-sigkill-exec-stop-post-restores-old-route")

    manager("start",CONTROL);ready()
    restored();stop();checks.append("systemd-expiration-restores-old-route-without-human-action")

    DROPIN.write_bytes(b"# INVENTED-FOREIGN-DROPIN-PRESERVE\n")
    manager("daemon-reload")
    manager("start",CONTROL,check=False);time.sleep(.5)
    require(DROPIN.read_bytes()==b"# INVENTED-FOREIGN-DROPIN-PRESERVE\n","FOREIGN_DROPIN_REPLACED")
    manager("stop",CONTROL,check=False);DROPIN.unlink();manager("daemon-reload")
    old_routes();checks.append("foreign-runtime-dropin-refused-and-preserved")
    return {"passed":True,"checks":checks,"helper_functions_unmodified":True,"nginx_real":True,
            "nginx_binary":original["executable"],"nginx_sha256":original["executable_sha256"],
            "service_starts_only":"synthetic nginx and synthetic control/socket","private_data_read":False}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        line=self.rfile.readline(8193).decode("ascii").strip().split()
        if len(line)!=3:return
        headers={}
        while True:
            raw=self.rfile.readline(8193)
            if raw==b"\r\n":break
            if not raw:return
            key,value=raw.decode("ascii").strip().split(":",1);headers[key.lower()]=value.strip()
        body=json.dumps({"path":line[1],"host":headers.get("host"),"authorization":"authorization" in headers,
                         "cookie":"cookie" in headers,"origin":headers.get("origin")}).encode()
        self.wfile.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "+str(len(body)).encode()+b"\r\nConnection: close\r\n\r\n"+body)


def socket_fixture():
    SOCKET.parent.mkdir(mode=0o750)
    os.chown(SOCKET.parent,0,60);os.chmod(SOCKET.parent,0o750)
    with socketserver.UnixStreamServer(str(SOCKET),Handler) as server:
        os.chown(SOCKET,0,60);os.chmod(SOCKET,0o660)
        server.serve_forever()


if __name__=="__main__":
    if sys.argv==[sys.argv[0],"socket"]:socket_fixture()
    elif sys.argv==[sys.argv[0],"qualify"]:
        try:print(json.dumps(qualify(),sort_keys=True))
        except Exception as error:
            locations=[{"file":Path(f.filename).name,"line":f.lineno,"function":f.name} for f in traceback.extract_tb(error.__traceback__)]
            print(json.dumps({"passed":False,"code":str(error) if isinstance(error,RuntimeError) else type(error).__name__,"synthetic_failure_locations":locations}))
            raise SystemExit(1)
    else:raise SystemExit(64)
