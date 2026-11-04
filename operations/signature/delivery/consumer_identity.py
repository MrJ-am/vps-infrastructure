"""Install independently checked Signature bytes into disposable frontend builds.

Call after the existing source/style checks and before artifact.json. This
module never edits candidate sources, a live site, or delivery permissions.
The caller supplies bytes already bound to the observed Signature commit and
independently regenerated; arbitrary candidate input must not call this layer.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import stat

BASE = ('signature.css','MrJamSignature.woff2','EchoPoint.woff2')
SOURCE_PATHS = {'signature.css':'web/signature.css','MrJamSignature.woff2':'web/MrJamSignature.woff2',
                'EchoPoint.woff2':'web/EchoPoint.woff2','Echologo.svg':'artwork/Echologo.svg',
                'Parisienne-Regular.ttf':'fonts/Parisienne-Regular.ttf','Parisienne-OFL.txt':'fonts/Parisienne-OFL.txt'}
INPUTS = set(SOURCE_PATHS.values()) | {'mrjam.sty','web/geometry.json'}
EXTRA = {
    'audition': ('Parisienne-Regular.ttf','Parisienne-OFL.txt'),
    'log': ('Echologo.svg',), 'logique': ('Echologo.svg',),
    'mateval': ('Echologo.svg',),
    'style': ('Echologo.svg','Parisienne-Regular.ttf','Parisienne-OFL.txt'),
    'vision': ('Echologo.svg','Parisienne-Regular.woff2','Parisienne-OFL.txt'),
}


def require(value, code):
    if not value:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()


def regular(path, *, immutable=False):
    require(not any(p.is_symlink() for p in (path,*path.parents)), 'SIGNATURE_ASSET_LINK_REFUSED')
    info=path.lstat()
    require(stat.S_ISREG(info.st_mode) and (immutable or info.st_nlink==1) and info.st_size<=16*1024**2,
            'SIGNATURE_ASSET_FILE_REFUSED')
    return path.read_bytes()


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()


def load(bundle, source, revision):
    """Rebind the fixed isolated job's result to the verified read-only input."""
    require(bundle.is_dir() and not bundle.is_symlink(), 'SIGNATURE_BUNDLE_REFUSED')
    names=set(SOURCE_PATHS)|{'Parisienne-Regular.woff2'}
    require({p.name for p in bundle.iterdir()}==names|{'manifest.json'}, 'SIGNATURE_BUNDLE_FILES_REFUSED')
    raw=regular(bundle/'manifest.json');require(len(raw)<=65536, 'SIGNATURE_MANIFEST_SIZE_REFUSED')
    manifest=json.loads(raw)
    require(set(manifest)=={'schema_version','revision','deployment_authorized','input_sha256',
                           'resources','regeneration','conversion'}
            and type(manifest['schema_version']) is int and manifest['schema_version']==1
            and manifest['revision']==revision and manifest['deployment_authorized'] is False,
            'SIGNATURE_BUNDLE_BINDING_REFUSED')
    inputs={name:regular(source/name,immutable=True) for name in sorted(INPUTS)}
    require(manifest['input_sha256']=={name:sha(data) for name,data in inputs.items()},
            'SIGNATURE_BUNDLE_SOURCE_CHANGED')
    require(set(manifest['resources'])==names, 'SIGNATURE_BUNDLE_RESOURCE_SET_REFUSED')
    resources={name:regular(bundle/name) for name in names}
    for name,raw in resources.items():
        row=manifest['resources'][name]
        require(set(row)=={'bytes','sha256'} and type(row['bytes']) is int
                and row['bytes']==len(raw) and row['sha256']==sha(raw), 'SIGNATURE_BUNDLE_BYTES_CHANGED')
        if name in SOURCE_PATHS:
            require(raw==inputs[SOURCE_PATHS[name]], 'SIGNATURE_BUNDLE_INPUT_CHANGED')
    require(all(manifest['regeneration'].get(k) is True for k in
                ('regeneration_verified','font_and_css_bytes_exact','geometry_values_equal','unicode_mapping_verified')),
            'SIGNATURE_REGENERATION_NOT_VERIFIED')
    conversion=manifest['conversion']
    require(conversion['source_sha256']==sha(inputs['fonts/Parisienne-Regular.ttf'])
            and conversion['sha256']==sha(resources['Parisienne-Regular.woff2'])
            and conversion['outlines_metrics_hints_preserved'] is True, 'SIGNATURE_CONVERSION_NOT_BOUND')
    return resources


def apply(site, frontend, revision, resources, *, version_mateval):
    site=Path(site)
    require(site.is_dir() and not any(p.is_symlink() for p in (site,*site.parents)),
            'SIGNATURE_SITE_REFUSED')
    require(not (site/'artifact.json').exists() and not (site/'artifact.json').is_symlink(),
            'SIGNATURE_ALREADY_MANIFESTED')
    require(type(revision) is str and re.fullmatch('[0-9a-f]{40}',revision), 'SIGNATURE_REVISION_REFUSED')
    require(frontend in {*EXTRA,'style-logo'}, 'SIGNATURE_CONSUMER_REFUSED')
    if frontend=='style-logo':
        require(not any((site/'assets/mrjam'/name).exists() for name in BASE),
                'SIGNATURE_UNEXPECTED_CONSUMER')
        return {'frontend':frontend,'revision':revision,'resources':[],'deployment_authorized':False}
    require(set(resources)==set(BASE)|{'Echologo.svg','Parisienne-Regular.ttf',
                                     'Parisienne-Regular.woff2','Parisienne-OFL.txt'},
            'SIGNATURE_RESOURCE_SET_REFUSED')
    require(all(type(data) is bytes and 0<len(data)<=16*1024**2 for data in resources.values()),
            'SIGNATURE_RESOURCE_BYTES_REFUSED')
    prefixes=('', 'admin/') if frontend=='mateval' else ('',)
    changes={}
    for prefix in prefixes:
        for name in BASE+EXTRA[frontend]:
            target=prefix+'assets/mrjam/'+name
            regular(site/target)  # Existing distribution boundary; no new fonts.
            changes[target]=resources[name]
        licence=prefix+'assets/mrjam/Parisienne-OFL.txt'
        if (site/licence).exists() or (site/licence).is_symlink():
            regular(site/licence)
        changes[licence]=resources['Parisienne-OFL.txt']
    if frontend=='mateval':
        for prefix in prefixes:
            base=prefix+'assets/mrjam/'
            identity=json.loads(regular(site/(base+'identite.json')))
            provenance=json.loads(regular(site/(base+'polices.json')))
            require(identity['depot']==provenance['depot']=='MrJ-am/Signature', 'SIGNATURE_PROVENANCE_REFUSED')
            require(set(identity['fichiers'])=={'Echologo.svg','signature.css'}
                    and set(provenance['fichiers'])=={'MrJamSignature.woff2','EchoPoint.woff2'}
                    and set(identity['ressources_externes'])=={'web/MrJamSignature.woff2','web/EchoPoint.woff2'},
                    'SIGNATURE_PROVENANCE_FIELDS_REFUSED')
            identity,provenance=copy.deepcopy(identity),copy.deepcopy(provenance)
            identity['revision']=provenance['revision']=revision
            for name in identity['fichiers']:
                identity['fichiers'][name]={'source':('artwork/' if name.endswith('.svg') else 'web/')+name,
                                          'git_blob':blob(resources[name]),'sha256':sha(resources[name])}
            for name in provenance['fichiers']:
                provenance['fichiers'][name]={'git_blob':blob(resources[name]),'sha256':sha(resources[name])}
                identity['ressources_externes']['web/'+name]=blob(resources[name])
            changes[base+'identite.json']=encoded(identity)
            changes[base+'polices.json']=encoded(provenance)
        metadata=json.loads(regular(site/'interface.json'))
        require(set(metadata)=={'application','style','signature'}, 'SIGNATURE_INTERFACE_FIELDS_REFUSED')
        metadata['signature']=revision;changes['interface.json']=encoded(metadata)
    if frontend=='vision':
        metadata=json.loads(regular(site/'manifest.json'))
        require(set(metadata)=={'revisionStyle','revisionSignature','revisionApplication',
                               'formatVersion','validation','fichiers'}, 'SIGNATURE_VISION_FIELDS_REFUSED')
        files={}
        for path in sorted(site.rglob('*')):
            require(not path.is_symlink(), 'SIGNATURE_ASSET_LINK_REFUSED')
            if not path.is_dir() and path!=site/'manifest.json':
                files[str(path.relative_to(site))]=sha(regular(path))
        require(len(files)<=2048, 'SIGNATURE_ASSET_LIMIT')
        files.update({name:sha(raw) for name,raw in changes.items()})
        metadata['revisionSignature']=revision;metadata['fichiers']=files
        changes['manifest.json']=encoded(metadata)
    # Validation above completes before touching the disposable assembly.
    for name,data in changes.items():
        (site/name).write_bytes(data)
    if frontend=='mateval':
        version_mateval(site)  # Canonical routine, never a candidate callback.
    return {'frontend':frontend,'revision':revision,'resources':sorted(changes),
            'deployment_authorized':False}
