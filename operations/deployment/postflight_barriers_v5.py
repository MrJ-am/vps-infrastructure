#!/usr/bin/env python3
"""Closed read-only metadata observation after the exact first promotion.

No service action, network request, secret content, application row or journal.
The bounded command reader follows preflight_adoption.py. No caller arguments.
"""
import grp
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

PROMOTED = '/nix/store/dc09bjfaf8wsfrwxpkqw0bi3xhp3nklm-nixos-system-srv1982677-26.05pre-git'
SYSTEMCTL = '/nix/store/0xiinbh7pbj479i5v28mqnjrvhvbdibf-systemd-260.2/bin/systemctl'
SSHD = '/nix/store/28hprrw9sdi4iarzyxa3r1a22b3dq5pn-openssh-10.5p1/bin/sshd'
SSH_HASH = '288a16fdcd039ae2a7d5c3ec4b0d7d806c0d16a1ae4eb6bd02f39909eeed84db'
NGINX_CONFIG = '/nix/store/9mhmiqk0cfy419vfkxaxhdhnf6pjd734-nginx.conf'
IPTABLES = '/nix/store/055skq6qnzl8pyhhzycp25nlnz4dy547-iptables-1.8.13/bin/'
ENVIRONMENT = {'PATH':'/run/current-system/sw/bin','LANG':'C','LC_ALL':'C','HOME':'/var/empty'}
DEADLINE = None
WORKERS = {
    'mrjam-rust-blue':(941,941),'mrjam-rust-green':(942,942),
    'mrjam-vision-archive':(943,943),'mrjam-vision-replay':(944,944),
    'mrjam-vision-cycle':(945,945),'mrjam-vision-closure':(946,946),
    'mrjam-vision-admission':(947,947),'mrjam-identity-deletion':(948,944),
    'mrjam-identity':(984,940),
}
USERS = {name:('mrjam-metier' if name=='mrjam-identity' else name) for name in WORKERS}
LEGACY = ('mrjam-metier','vision','matheval','vise','mrj-auth','mrjam-courriel',
          'vision-cycle','vision-archive','vision-replay','vision-closure','vision-admission',
          'vision-purge','vision-embeddings-backfill','vise-provision','vise-backup')
BACKUPS = ('mrjam-sauvegarde','forgejo-backup','nextcloud-backup',
           'postgresqlBackup-matheval','postgresqlBackup-nextcloud')
TEMPORARY = ('mrjam-kanidm-passkey-portal','mrjam-passkey-nginx-route','mrjam-kanidm-worker-provision')
SERVICES = tuple(dict.fromkeys(tuple(WORKERS)+LEGACY+BACKUPS+TEMPORARY+('sshd','nginx','firewall')))
PROPERTIES = ('Id','LoadState','ActiveState','UnitFileState','MainPID','FragmentPath','DropInPaths',
              'User','Group','NoNewPrivileges','CapabilityBoundingSet','AmbientCapabilities',
              'ProtectSystem','ProtectHome','NextElapseUSecRealtime','Persistent')
SECRET_FILES = {
    **{role+'_token':'/var/lib/mrjam-identite/kanidm-'+role+'.token' for role in ('admission','cycle','replay')},
    'identity_client':'/var/lib/mrjam-identite/kanidm-vision.secret',
    **{name:'/var/lib/mrjam-worker-credentials/v1/'+name for name in
       ('smtp.json','archive.json','archive-initialize.json','recipient','closure','approval')},
}


def run(arguments):
    """Fixed executable/arguments only; bounded time/output and no stderr."""
    remaining = min(5., DEADLINE-time.monotonic()) if DEADLINE else 5.
    if remaining<=0:raise ValueError()
    process=None
    try:
        process=subprocess.Popen(arguments,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env=ENVIRONMENT,start_new_session=True)
        end=time.monotonic()+remaining;data=bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while True:
                left=end-time.monotonic()
                if left<=0 or not selector.select(left):raise ValueError()
                chunk=os.read(process.stdout.fileno(),8192)
                if not chunk:break
                data.extend(chunk)
                if len(data)>262144:raise ValueError()
        if process.wait(timeout=max(.01,end-time.monotonic()))!=0:raise ValueError()
        return data.decode('utf-8','strict').strip()
    finally:
        if process is not None:
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait(timeout=1)
            process.stdout.close()


def read_public(path,maximum=262144):
    # Called only for immutable public configuration and fixed /proc metadata.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError()
        raw=os.read(fd,maximum+1)
        if len(raw)>maximum:raise ValueError()
        return raw
    finally:os.close(fd)


def protected(path,directory=False,uid=0,gid=0,mode=0o600):
    try:
        item=os.lstat(path)
        return {'present':True,'expected_metadata':
            (stat.S_ISDIR(item.st_mode) if directory else stat.S_ISREG(item.st_mode))
            and item.st_uid==uid and item.st_gid==gid and stat.S_IMODE(item.st_mode)==mode
            and (directory or item.st_nlink==1)}
    except FileNotFoundError:return {'present':False,'expected_metadata':False}


def parse_units(raw,expected):
    result={}
    for block in raw.split('\n\n'):
        fields={}
        for line in block.splitlines():
            key,separator,value=line.partition('=')
            if not separator or key not in PROPERTIES or key in fields:raise ValueError()
            fields[key]=value
        name=fields.get('Id')
        if name not in expected or name in result:raise ValueError()
        result[name]=fields
    if set(result)!=set(expected):raise ValueError()
    return result


def stopped(item):
    return item.get('ActiveState') in ('inactive','failed') and item.get('MainPID','0')=='0'


def process_barriers(pid,uid,gid):
    if not re.fullmatch('[1-9][0-9]{0,8}',pid):return {'running_observed':False}
    fields={line.split(':',1)[0]:line.split(':',1)[1].strip()
            for line in read_public('/proc/'+pid+'/status',16384).decode().splitlines() if ':' in line}
    return {'running_observed':True,
        'uids_match':fields.get('Uid','').split()==[str(uid)]*4,
        'gids_match':fields.get('Gid','').split()==[str(gid)]*4,
        'no_effective_or_ambient_caps':all(re.fullmatch('0+',fields.get(key,'')) is not None for key in ('CapEff','CapAmb')),
        'no_new_privileges':fields.get('NoNewPrivs')=='1'}



QUALIFIED_WORKER_UNITS_SHA256 = {'mrjam-identity': '3a7c4df3c55b533371333fdd6a2d7f54024658c46a6ca6cbab078296b829f6a0', 'mrjam-identity-deletion': '57e9768c72268b149b18af2dec4ed2c6266e1e3dcb75b06044778f6bf9093c5d', 'mrjam-rust-blue': '52b16f3a45bead0db4d1ebb162429dc89ec4eae3a2fbb23c784e0c2985601f55', 'mrjam-rust-green': '4840fb095f8e3f11954da8b1ea8435dce99125d0b92e0b0dbade6c4cef10ac66', 'mrjam-vision-admission': '0b1801682213548e3c5153a42f3b93e99af2deeae9166af0503add6e12c700fb', 'mrjam-vision-archive': '00225c1a32aa3daac84324f0e8fb757cd5137eccbec00a654ae31c694890b746', 'mrjam-vision-closure': '32a550f8727efc9e1b90f2a171c6afea7838705cb4bb7f3126b7380094520d46', 'mrjam-vision-cycle': '7b386821ba62eb77e29454e09e9b9a05ec60d51e1344cfbe593a1388295dba93', 'mrjam-vision-replay': '4278c5cfb8e368e347345ff44f12787272bc33d7245884775501615ca6b95277'}

def fragment_matches_promoted(name,item):
    # PID1 may retain /etc or /run spelling instead of the final store target.
    # Follow only public unit paths for this exact, fixed unit name; never read
    # arbitrary contents from FragmentPath, and never accept content equality
    # as a substitute for the promoted immutable target.
    if name not in (*WORKERS,'sshd','nginx'):raise ValueError()
    unit=name+'.service'
    expected=Path(PROMOTED+'/etc/systemd/system/'+unit).resolve(strict=True)
    if not str(expected).startswith('/nix/store/'):raise ValueError()
    actual=item.get('FragmentPath','')
    fixed={str(expected),PROMOTED+'/etc/systemd/system/'+unit,
           '/etc/systemd/system/'+unit,'/etc/static/systemd/system/'+unit,
           '/run/systemd/system/'+unit,'/run/current-system/etc/systemd/system/'+unit}
    public_store_unit=re.fullmatch(r'/nix/store/[0-9abcdfghijklmnpqrsvwxyz]{32}-(?:system-units|unit-'+re.escape(unit)+r')/'+re.escape(unit),actual)
    if actual not in fixed and public_store_unit is None:return False
    try:return Path(actual).resolve(strict=True)==expected
    except (OSError,RuntimeError):return False


def worker(name,item):
    uid,gid=WORKERS[name];account=pwd.getpwnam(USERS[name])
    groups=os.getgrouplist(USERS[name],account.pw_gid)
    try:wheel=grp.getgrnam('wheel').gr_gid
    except KeyError:wheel=0
    expected_group='mrjam-log-readers' if name=='mrjam-identity' else 'mrjam-vision-replay' if name=='mrjam-identity-deletion' else name
    expected=str(Path(PROMOTED+'/etc/systemd/system/'+name+'.service').resolve(strict=True))
    inactive_slot_unavailable=name=='mrjam-rust-green' and item.get('LoadState') in ('masked','not-found')
    matches=None if inactive_slot_unavailable else fragment_matches_promoted(name,item)
    account_gid=984 if name=='mrjam-identity' else gid
    return {'identity_matches':account.pw_uid==uid and account.pw_gid==account_gid,
        'no_root_or_wheel_membership':0 not in groups and wheel not in groups,
        'fragment_matches_promoted':matches,
        'unit_load_state':item.get('LoadState') if item.get('LoadState') in ('loaded','masked','not-found','error','bad-setting','stub','merged') else 'unavailable',
        'qualified_declaration_matches':hashlib.sha256(read_public(expected)).hexdigest()==QUALIFIED_WORKER_UNITS_SHA256[name],
        'inactive_slot_expected':(inactive_slot_unavailable and stopped(item)) if name=='mrjam-rust-green' else None,
        'no_dropins':item.get('DropInPaths')=='',
        'unit_user_group_match':None if inactive_slot_unavailable else item.get('User')==USERS[name] and item.get('Group')==expected_group,
        'unit_no_capabilities':None if inactive_slot_unavailable else item.get('CapabilityBoundingSet')==item.get('AmbientCapabilities')=='',
        'unit_no_new_privileges':None if inactive_slot_unavailable else item.get('NoNewPrivileges')=='yes',
        'unit_protected_filesystem':None if inactive_slot_unavailable else item.get('ProtectSystem')=='strict' and item.get('ProtectHome') in ('yes','read-only','tmpfs'),
        'replay_declaration_has_no_provider_token':(matches is True and item.get('DropInPaths')==''
            and b'kanidm-replay.token' not in read_public(expected)) if name=='mrjam-vision-replay' else None,
        'process':process_barriers(item.get('MainPID','0'),uid,gid)}


def listeners(raw,ipv6=False):
    observed=[]
    for line in raw.decode('ascii').splitlines()[1:]:
        fields=line.split()
        if len(fields)<4:raise ValueError()
        if fields[3]!='0A':continue
        address,port=fields[1].split(':')
        data=bytes.fromhex(address)
        data=b''.join(data[i:i+4][::-1] for i in range(0,len(data),4))
        ip=ipaddress.ip_address(data)
        if ipv6!=isinstance(ip,ipaddress.IPv6Address):raise ValueError()
        observed.append((int(port,16),ip.is_loopback or (ip.version==6 and ip.ipv4_mapped is not None and ip.ipv4_mapped.is_loopback)))
    return observed


def firewall_family(executable):
    chains={name:run([IPTABLES+executable,'-w','1','-S',name]).splitlines()
            for name in ('INPUT','nixos-fw','nixos-fw-accept','nixos-fw-refuse')}
    rules=chains['nixos-fw'][1:]
    ports=[];unrecognized=False
    for rule in rules:
        match=re.fullmatch(r'-A nixos-fw -p tcp -m tcp --dport ([0-9]+) -j nixos-fw-accept',rule)
        if match:ports.append(int(match.group(1)));continue
        if rule in ('-A nixos-fw -i lo -j nixos-fw-accept',
                    '-A nixos-fw -m conntrack --ctstate RELATED,ESTABLISHED -j nixos-fw-accept',
                    '-A nixos-fw -m conntrack --ctstate ESTABLISHED,RELATED -j nixos-fw-accept',
                    '-A nixos-fw -j nixos-fw-log-refuse',
                    '-A nixos-fw -p icmp -m icmp --icmp-type 8 -j nixos-fw-accept',
                    '-A nixos-fw -p ipv6-icmp -m icmp6 --icmpv6-type 137 -j DROP',
                    '-A nixos-fw -p ipv6-icmp -m icmp6 --icmpv6-type 139 -j DROP',
                    '-A nixos-fw -p ipv6-icmp -j nixos-fw-accept',
                    '-A nixos-fw -d fe80::/64 -p udp -m udp --dport 546 -j nixos-fw-accept'):continue
        unrecognized=True
    log=run([IPTABLES+executable,'-w','1','-S','nixos-fw-log-refuse']).splitlines()
    return {'input_enters_only_expected_chain':chains['INPUT']==['-P INPUT ACCEPT','-A INPUT -j nixos-fw'],
        'public_tcp_ports_exact':sorted(ports)==[22,80,443,2222],
        'no_unrecognized_input_exception':not unrecognized,
        'terminal_drop_present':bool(rules) and rules[-1]=='-A nixos-fw -j nixos-fw-log-refuse'
           and log[-1:] == ['-A nixos-fw-log-refuse -j nixos-fw-refuse']
           and chains['nixos-fw-refuse']==['-N nixos-fw-refuse','-A nixos-fw-refuse -j DROP'],
        'accept_chain_exact':chains['nixos-fw-accept']==['-N nixos-fw-accept','-A nixos-fw-accept -j ACCEPT']}


def ssh(item):
    public=Path('/etc/ssh/sshd_config').resolve()
    if not str(public).startswith('/nix/store/') or hashlib.sha256(read_public(public)).hexdigest()!=SSH_HASH:
        return {'configuration_matches_promoted':False}
    # -G only parses/prints configuration. It does not load host private keys.
    raw=run([SSHD,'-G','-f','/etc/ssh/sshd_config'])
    values={line.split(' ',1)[0].lower():line.split(' ',1)[1] for line in raw.splitlines() if ' ' in line}
    pid=item.get('MainPID','0')
    running=read_public('/proc/'+pid+'/cmdline',8192) if re.fullmatch('[1-9][0-9]{0,8}',pid) else b''
    return {'configuration_matches_promoted':True,
        'active':item.get('ActiveState')=='active',
        'unit_matches_promoted':fragment_matches_promoted('sshd',item),
        'no_runtime_dropins':item.get('DropInPaths')=='',
        'running_expected_configuration':SSHD.encode() in running and b'/etc/ssh/sshd_config' in running and re.search(rb'(?:^|[\x00 \t])-o',running) is None,
        'password_disabled':values.get('passwordauthentication')=='no',
        'keyboard_interactive_disabled':values.get('kbdinteractiveauthentication')=='no',
        'root_key_only':values.get('permitrootlogin') in ('prohibit-password','without-password'),
        'port_22_only':re.findall(r'^port (.+)$',raw,re.M|re.I)==['22'],
        'root_ssh_is_full_administration':True}


def nginx(item):
    command=run([SYSTEMCTL,'show','nginx.service','--property=ExecStart','--value'])
    pid=item.get('MainPID','0')
    running=read_public('/proc/'+pid+'/cmdline',8192) if re.fullmatch('[1-9][0-9]{0,8}',pid) else b''
    return {'active':item.get('ActiveState')=='active',
        'unit_matches_promoted':fragment_matches_promoted('nginx',item),
        'unit_selects_promoted_configuration':NGINX_CONFIG in command,
        'running_master_selects_promoted_configuration':NGINX_CONFIG.encode() in running,
        'no_runtime_dropins':item.get('DropInPaths')=='',
        'temporary_portal_route_absent_from_promoted_configuration':b'_mrjam-worker-provision' not in read_public(NGINX_CONFIG)}


def optional(function,*arguments):
    try:return {'observed':True,'checks':function(*arguments)}
    except Exception:return {'observed':False,'checks':{}}


def collect():
    names=[name+'.service' for name in SERVICES]+[name+'.timer' for name in BACKUPS]
    units=parse_units(run([SYSTEMCTL,'show',*names,'--property='+','.join(PROPERTIES)]),set(names))
    network=listeners(read_public('/proc/net/tcp'))+listeners(read_public('/proc/net/tcp6'),True)
    public={port for port,loopback in network if not loopback}
    secrets={name:protected(path) for name,path in SECRET_FILES.items()}
    for name,path in (('identity_directory','/var/lib/mrjam-identite'),('worker_directory','/var/lib/mrjam-worker-credentials/v1')):
        secrets[name]=protected(path,directory=True,mode=0o700)
    return {'schema_version':1,'code':'BARRIERS_OBSERVED',
        'promoted_live_and_boot':all(os.path.realpath(path)==PROMOTED for path in ('/run/current-system','/nix/var/nix/profiles/system')),
        'only_root_has_uid_zero':[(entry.pw_name,entry.pw_uid) for entry in pwd.getpwall() if entry.pw_uid==0]==[('root',0)],
        'workers':{name:optional(worker,name,units[name+'.service']) for name in WORKERS},
        'secret_metadata':secrets,
        'listeners':{'public_tcp_only_22_80_443_2222':public<={22,80,443,2222},
                     'expected_public_tcp_present':{str(port):port in public for port in (22,80,443,2222)},
                     'private_application_ports_loopback_only':all(loopback for port,loopback in network if port in (3002,3004,5432,8443,38101,38102))},
        'firewall':{family:optional(firewall_family,binary) for family,binary in (('ipv4','iptables'),('ipv6','ip6tables'))},
        'ssh':optional(ssh,units['sshd.service']),'nginx':optional(nginx,units['nginx.service']),
        'legacy':{name:{'stopped':stopped(units[name+'.service']),
                        'not_enabled':units[name+'.service'].get('UnitFileState') in ('','disabled','masked','masked-runtime','not-found'),
                        'not_loaded_or_masked':units[name+'.service'].get('LoadState') in ('not-found','masked')}
                  for name in LEGACY},
        'temporary_administration_stopped':{name:stopped(units[name+'.service']) for name in TEMPORARY},
        'vise_retained_directory':{'present':Path('/var/lib/etp-carnet').is_dir(),
                                   'content_preservation_proved':False},
        'backups':{name:{'active_timer':units[name+'.timer'].get('ActiveState')=='active',
                         'persistent_timer':units[name+'.timer'].get('Persistent')=='yes',
                         'future_elapse_scheduled':units[name+'.timer'].get('NextElapseUSecRealtime','') not in ('','n/a','0'),
                         'successful_restore_proved':False}
                   for name in BACKUPS},
        'secrets_read':False,'application_records_read':False,'journals_read':False,'production_mutation':False,
        'future_ci_proved':False,'application_authorization_proved':False}


def main():
    global DEADLINE
    if len(sys.argv)!=1 or os.geteuid()!=0:return 64
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    DEADLINE=time.monotonic()+55
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError()))
    signal.alarm(60)
    try:value=collect();code=0
    except Exception:value={'schema_version':1,'code':'BARRIERS_UNAVAILABLE'};code=1
    finally:signal.alarm(0)
    print(json.dumps(value,sort_keys=True,separators=(',',':')))
    return code


if __name__=='__main__':raise SystemExit(main())
