"""Publish one real external rules audit, never a review or a merge.

No candidate Python is imported here. Exact immutable report bytes are selected
by the operator, independently of the rules repository and application jobs.
"""
import hashlib
from pathlib import Path
import re
import tempfile
import core
import lease
import protection
import reconcile

HEAD = '470211d7b2522322a94c5ddfc6770d833bb1457e'
BASE = core.BASE
REPORT_SHA256 = '01c207fc0880e270a597c0d3a4657bd1b3e95df3355aab267d96b3d4f484bdba'
PULL = BASE + '/pulls/2'
COMMIT = BASE + '/git/commits/' + HEAD
STATUSES = BASE + '/commits/' + HEAD + '/statuses?limit=50&page=1'
POST = BASE + '/statuses/' + HEAD
BODY = {'state':'success', 'context':'mrjam/independent-validation',
    'description':'Audit externe des règles : 19 tests ; preuve 01c207fc0880',
    'target_url':'https://forge.mrj.am/MrJ-am/mrjam-validation/pulls/2'}


def checked_report(raw, binding):
    core.require(type(raw) is bytes and len(raw) < 16384
        and hashlib.sha256(raw).hexdigest() == REPORT_SHA256, 'AUDIT_BYTES_REFUSED')
    report = reconcile.parse(raw)
    core.require(report['head'] == HEAD == binding.value['head']
        and all(report[k] == binding.value[k] for k in ('base','tree'))
        and report['repository'] == 'MrJ-am/mrjam-validation'
        and report['status'] == 'passed' and report['tests'] == 19
        and report['skipped'] == 0 and report['proposal_files_verified'] == 21
        and report['forgejo_actions_run_id'] is None
        and report['adoption_authorized'] is False and report['deployment_authorized'] is False
        and report['commit_status_published'] is False
        and report['isolation'] == {'unprivileged':True,'private_host_paths_absent':True,
            'network_interfaces':['lo']}, 'AUDIT_RESULT_REFUSED')
    return report


class Transport(core.Transport):
    def endpoint_allowed(self, method, path):
        return (method == 'GET' and (path in (PULL, COMMIT, STATUSES, '/api/v1/settings/api')
            or super().endpoint_allowed(method,path)) or method == 'POST' and path == POST)

    def request(self, method, path, body=None, *, missing=False):
        core.require(body == BODY if method == 'POST' else body is None, 'AUDIT_BODY_REFUSED')
        return super().request(method,path,body,missing=missing)


def observe(api, binding, bootstrap):
    observed = core.observe(api,binding,bootstrap)
    core.require(core.validate_pr(api.request('GET',PULL),binding,observed) == 2,
        'AUDIT_PULL_REFUSED')
    commit = api.request('GET',COMMIT)
    core.require(type(commit) is dict and commit.get('sha') == HEAD
        and type(commit.get('parents')) is list and len(commit['parents']) == 1
        and commit['parents'][0].get('sha') == binding.value['base'], 'AUDIT_COMMIT_REFUSED')
    return observed


def verify_git(git, binding):
    # Forgejo 17 commit.tree.sha is the commit ID (documented native finding).
    # Fetch only this branch, then resolve the actual Git objects independently.
    expected={'refs/heads/main':binding.value['base'],binding.ref:HEAD}
    core.require(git.refs()==expected,'REFERENCE_OBSERVATION_CHANGED')
    with tempfile.TemporaryDirectory(prefix='rules-audit-') as root:
        path=str(Path(root)/'objects.git')
        git.command(['init','--bare','--initial-branch=main',path])
        git.command(['-C',path,'fetch','--depth=2','--no-tags','--no-recurse-submodules',
            core.URL,binding.ref+':refs/heads/proposal'])
        core.require(git.command(['-C',path,'rev-list','--parents','-n','1',HEAD]).strip()
            == (HEAD+' '+binding.value['base']).encode(),'PROPOSAL_PARENT_REFUSED')
        core.require(git.command(['-C',path,'rev-parse',HEAD+'^{tree}']).strip()
            == binding.value['tree'].encode(),'PROPOSAL_TREE_REFUSED')
        core.require(git.command(['-C',path,'diff-tree','--no-commit-id','--name-status','-r',
            '--no-renames','-z',binding.value['base'],HEAD]) ==
            b''.join(b'A\0'+name.encode()+b'\0' for name in sorted(binding.value['files'])),
            'PROPOSAL_DELTA_REFUSED')
        for name,digest in {**binding.value['files'],core.WORKFLOW:binding.value['workflow_sha256']}.items():
            entry=git.command(['-C',path,'ls-tree','-z',HEAD,'--',name])
            core.require(re.fullmatch(rb'100644 blob [0-9a-f]{40}\t'+re.escape(name.encode())+rb'\x00',entry),
                'WORKFLOW_MODE_REFUSED')
            core.require(hashlib.sha256(git.command(['-C',path,'show',HEAD+':'+name])).hexdigest()==digest,
                'WORKFLOW_BYTES_REFUSED')
    core.require(git.refs()==expected,'REFERENCE_READBACK_REFUSED')


def status(api, author_id):
    settings = api.request('GET','/api/v1/settings/api')
    core.require(type(settings) is dict and type(settings.get('max_response_items')) is int
        and settings['max_response_items'] >= 50, 'AUDIT_STATUS_PAGE_REFUSED')
    rows = api.request('GET',STATUSES)
    if rows is None: rows = []
    core.require(type(rows) is list and len(rows) < 50 and all(type(r) is dict for r in rows),
        'AUDIT_STATUS_PAGE_REFUSED')
    matches = [r for r in rows if r.get('context') == BODY['context']]
    core.require(len(matches) <= 1, 'AUDIT_STATUS_CONFLICT')
    for row in matches:
        core.require(all(row.get('status' if k == 'state' else k) == v for k,v in BODY.items())
            and row.get('creator',{}).get('id') == author_id
            and type(row.get('id')) is int and row['id'] > 0, 'AUDIT_STATUS_CONFLICT')
    return matches[0]['id'] if matches else None


def publish(raw, binding, bootstrap, git, *, transport=Transport):
    checked_report(raw,binding)  # Refuse before obtaining any credential.
    with lease.repository_lease(bootstrap) as token:
        api = transport(token,binding)
        before = observe(api,binding,bootstrap)
        with core.credentials.broker(token,core.REPO):
            verify_git(git,binding)
        prior = status(api,before['author_id'])
        if prior is None:
            core.require(observe(api,binding,bootstrap) == before, 'AUDIT_OBSERVATION_CHANGED')
            api.request('POST',POST,BODY)
        identifier = status(api,before['author_id'])
        core.require(identifier is not None, 'AUDIT_READBACK_REFUSED')
        core.require(observe(api,binding,bootstrap) == before, 'AUDIT_OBSERVATION_CHANGED')
    return {'schema_version':1,'code':'RULES_AUDIT_PUBLISHED','head':HEAD,
        'report_sha256':REPORT_SHA256,'status_id':identifier,'created':prior is None,
        'temporary_token_revoked':True,'forgejo_actions_run_id':None,
        'review_created':False,'merged':False,'deployed':False}
