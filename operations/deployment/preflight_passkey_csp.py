#!/usr/bin/env python3
"""Only closed CSP compatibility flags from the already pinned immutable code."""
import hashlib,json,os,re,stat,sys
PREVIOUS="/nix/store/jn9rf2fgk2y6dbhdnjwkmfww3pchkyb9-nixos-system-nixos-26.05.8639.c5c4a43b0e80"
CONFIG="/nix/store/g0v9ji72630xhgg5q3alz0883m7pjbkb-nginx.conf"
SHA256="8e540ab2d53da5b03132176e5947eb40cc17866e1dba939725b77901b8155857"
STORE=r"/nix/store/[0-9a-df-np-sv-z]{32}-[A-Za-z0-9+._?=-]+"

def require(value):
    if not value:
        raise ValueError("PASSKEY_NGINX_OBSERVATION_REFUSED")

def immutable(path, maximum, executable=False):
    require(re.fullmatch(STORE+r"(?:/[A-Za-z0-9+._=-]+)*",path) is not None)
    require(os.path.realpath(path)==path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,"rb") as source:
        meta=os.fstat(source.fileno())
        require(stat.S_ISREG(meta.st_mode) and meta.st_uid==0 and not stat.S_IMODE(meta.st_mode)&0o222)
        require(0<meta.st_size<=maximum and (not executable or stat.S_IMODE(meta.st_mode)&0o111))
        raw=source.read(maximum+1)
    require(len(raw)==meta.st_size)
    if executable:
        require(raw.startswith(b"\x7fELF"))
    return raw

def tokens(raw):
    """Small fail-closed Nginx tokenizer retaining byte insertion positions."""
    require(isinstance(raw,bytes) and len(raw)<=1024*1024 and b"\0" not in raw)
    # Latin-1 keeps a one-to-one mapping to byte offsets, including comments.
    text=raw.decode("latin1")
    out=[];word=[];start=None;quote=None;i=0
    while i<len(text):
        char=text[i]
        if char=="\\":
            require(i+1<len(text));start=i if start is None else start
            i+=1;word.append(text[i])
        elif quote:
            if char==quote:quote=None
            else:word.append(char)
        elif char in "\"'":
            start=i if start is None else start;quote=char
        elif char=="#":
            if start is not None:out.append(("".join(word),start,i));word=[];start=None
            end=text.find("\n",i);i=len(text) if end<0 else end
            continue
        elif char.isspace() or char in "{};":
            if start is not None:out.append(("".join(word),start,i));word=[];start=None
            if char in "{};":out.append((char,i,i+1))
        else:
            start=i if start is None else start;word.append(char)
        require(len(word)<=16384 and len(out)<=100000)
        i+=1
    require(quote is None and start is None)
    return out


def tree(raw):
    stream=tokens(raw);index=0
    def block(nested,depth):
        nonlocal index
        require(depth<=20)
        nodes=[];words=[]
        while index<len(stream):
            value,_,_=stream[index];index+=1
            if value=='}':
                require(nested and not words);return nodes
            if value in ('{',';'):
                require(words)
                nodes.append((words,block(True,depth+1) if value=='{' else None));words=[]
            else:words.append(value)
        require(not nested and not words);return nodes
    return block(False,0)


def compatible(policy):
    require(len(policy)<=8192 and '$' not in policy)
    directives={}
    for raw in policy.split(';'):
        words=raw.strip().split()
        if words and words[0] not in directives:directives[words[0]]=words[1:]
    def allowed(name,fallback):
        values=directives.get(name,directives.get(fallback,directives.get('default-src')))
        if values is None:return True
        if "'strict-dynamic'" in values and any(v.startswith(("'nonce-","'sha256-","'sha384-","'sha512-")) for v in values):return False
        return any(v in ("'self'",'*','https:','https://log.mrj.am') for v in values)
    sandbox=directives.get('sandbox')
    return {'script_self':allowed('script-src-elem','script-src'),
            'style_self':allowed('style-src-elem','style-src'),
            'connect_self':allowed('connect-src','connect-src'),
            'origin_and_scripts_unsandboxed':sandbox is None or ('allow-scripts' in sandbox and 'allow-same-origin' in sandbox)}


def observe():
    require(os.geteuid()==0 and os.path.realpath('/run/current-system')==PREVIOUS)
    raw=immutable(CONFIG,1024*1024);require(hashlib.sha256(raw).hexdigest()==SHA256)
    http=[children for words,children in tree(raw) if words==['http']]
    require(len(http)==1 and http[0] is not None)
    servers=[]
    for words,children in http[0]:
        if words==['server'] and children is not None:
            if any(w==['server_name','log.mrj.am'] for w,c in children) and any(w[0]=='listen' and 'ssl' in w for w,c in children):servers.append(children)
    require(len(servers)==1)
    parent=[w for w,c in http[0] if w[0]=='add_header']
    own=[w for w,c in servers[0] if w[0]=='add_header']
    inheritance=[w[1:] for w,c in servers[0] if w[0]=='add_header_inherit']
    if not inheritance:inheritance=[w[1:] for w,c in http[0] if w[0]=='add_header_inherit']
    require(not inheritance or inheritance in ([['on']],[['off']],[['merge']]))
    mode=inheritance[0][0] if inheritance else 'on'
    effective=parent+own if mode=='merge' else own if mode=='off' else own or parent
    policies=[w[2] for w in effective if len(w)>=3 and w[1].lower()=='content-security-policy']
    flags=[compatible(policy) for policy in policies]
    known_includes=all(len(w)==2 and re.fullmatch(STORE+r'/etc/nginx/mime.types',w[1]) for w,c in http[0] if w[0]=='include')
    return {'schema_version':1,'code':'PASSKEY_CSP_FLAGS_OBSERVED','configuration_sha256':SHA256,
            'inherited_csp_count':len(policies),'all_inherited_policies_allow_portal_self':all(all(p.values()) for p in flags),
            'per_policy_flags':flags,'http_includes_only_immutable_mime_types':known_includes,
            'server_includes_absent':not any(w[0]=='include' for w,c in servers[0]),
            'private_configuration_read':False,'production_mutation':False}


def main():
    if len(sys.argv)!=1:return 64
    try:result=observe()
    except Exception:
        print('{"schema_version":1,"code":"PASSKEY_CSP_OBSERVATION_REFUSED"}');return 1
    print(json.dumps(result,sort_keys=True,separators=(',',':')));return 0


if __name__=='__main__':raise SystemExit(main())
