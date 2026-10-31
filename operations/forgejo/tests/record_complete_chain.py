#!/usr/bin/env python3
"""Record the completed synthetic chain and compare public payload bytes."""
import hashlib
import json
from pathlib import Path
import tarfile

BASE = Path('/workspace/shared/mrjam-declarative-nix')
ROOT = Path(__file__).resolve().parents[3]
VALIDATION = Path('/workspace/mrjam-validation')
RUN = BASE/'complete-chain-run-20261031-02'
FIXTURE = BASE/'complete-chain-fixture-20261031-02'


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def members(path):
    result, manifests = {}, {}
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            require(member.isfile() and member.name not in result and
                not member.name.startswith('/') and '..' not in Path(member.name).parts,
                'ARCHIVE_MEMBER_REFUSED')
            raw = archive.extractfile(member).read()
            result[member.name] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                'mode': member.mode, 'uid': member.uid, 'gid': member.gid, 'mtime': member.mtime}
            if member.name.endswith('/artifact.json'):
                manifests[member.name] = json.loads(raw)
    return result, manifests


def main():
    execution = read(RUN/'execution.json')
    require(execution['exit_code'] == 0, 'SUCCESSFUL_EXECUTION_REQUIRED')
    lines = (RUN/'result.jsonl').read_text().splitlines()
    require(len(lines) == 1, 'ONE_CLOSED_RESULT_REQUIRED')
    result = json.loads(lines[0])
    require(result['decision'] == 'passed' and len(result['checks']) == 17 and
            all(v is True for v in result['checks'].values()), 'INTEGRATED_CHECK_FAILED')
    runtime = read(FIXTURE/'runtime.json')
    evidence = result['integration_evidence']
    require(evidence['worker_status'] == {'calls':1,'exit_codes':[0],'error':False,'uid':59990},
            'WORKER_EXECUTION_CHANGED')
    collector = read(RUN/'public-results/collector-status.json')
    require(collector == {'calls':2,'exit_codes':[0,0],'error':False,'uid':59991,'fixed_errors':[]},
            'COLLECTOR_EXECUTION_CHANGED')
    receipt = evidence['receipt']
    require(receipt['proposal_sha256'] == runtime['proposal_sha256'] and
            receipt['rules_revision'] == runtime['rules_revision'], 'RECEIPT_IDENTITY_CHANGED')
    payloads = RUN/'public-results/artifacts'
    for item in receipt['artifacts']:
        require(item['name'] in {'server','frontend.tar','verification.json'}, 'ARTIFACT_NAME_CHANGED')
        path = payloads/item['name']
        require(path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], 'ARTIFACT_CHANGED')
    verification = read(payloads/'verification.json')
    require(verification == evidence['verification'] and verification['decision'] == 'passed' and
            verification['production_authorized'] is False and
            verification['independent_adoption_established'] is False and
            all(step['status'] == 'passed' for step in verification['steps']), 'VERIFICATION_CHANGED')
    prior = read(VALIDATION/'workflow-runner/qualification-complete-pass-20261031-06.json')['result']
    old = BASE/'worker-complete-20261031-10-qualified-public'
    old_artifacts = {a['name']:a for a in prior['artifacts']}
    for name in ('server','frontend.tar'):
        require(sha(old/name) == old_artifacts[name]['sha256'], 'PREVIOUS_ARTIFACT_CHANGED')
    require((old/'server').read_bytes() == (payloads/'server').read_bytes(), 'SERVER_PAYLOAD_CHANGED')
    before, before_manifests = members(old/'frontend.tar')
    after, after_manifests = members(payloads/'frontend.tar')
    require(len(before) == len(after) == 449 and set(before) == set(after), 'FRONTEND_MEMBER_SET_CHANGED')
    manifests = {n+'/artifact.json' for n in ('audition','log','logique','mateval','style','style-logo','vision')}
    changed = {n for n in before if before[n] != after[n]}
    require(changed == manifests and set(before_manifests) == set(after_manifests) == manifests,
            'FRONTEND_PAYLOAD_CHANGED')
    for name in manifests:
        a, b = before_manifests[name], after_manifests[name]
        require(a['input_manifest_sha256'] == prior['proposal_sha256'] and
                b['input_manifest_sha256'] == runtime['proposal_sha256'], 'MANIFEST_BINDING_CHANGED')
        require(set(a) == set(b) and {k for k in a if a[k] != b[k]} == {'input_manifest_sha256'},
                'UNEXPECTED_MANIFEST_CHANGE')
        require({k:v for k,v in before[name].items() if k != 'sha256'} ==
                {k:v for k,v in after[name].items() if k != 'sha256'}, 'ARCHIVE_METADATA_CHANGED')
    comparison = {'server_identical_bytes':True,'frontend_payload_files_identical_bytes_and_metadata':442,
        'total_tar_members':449,'changed_manifests':sorted(manifests),
        'only_changed_manifest_field':'input_manifest_sha256',
        'previous_frontend_tar_sha256':sha(old/'frontend.tar'),
        'current_frontend_tar_sha256':sha(payloads/'frontend.tar'),
        'previous_proposal':prior['proposal_sha256'],'current_proposal':runtime['proposal_sha256'],
        'original_archive_and_hashes_preserved':True,'new_archive_automatically_selected_for_runtime':False}
    for name, expected in runtime['code_sha256'].items():
        require(sha(FIXTURE/'code/forgejo'/name) == expected and
                sha(ROOT/'operations/forgejo'/name) == expected, 'EXERCISED_CODE_CHANGED')
    nix = read(BASE/'complete-chain-nix-metadata-20261031-01.json')
    require(nix['current_derivations_match'] and nix['repeated_preparation_derivations_match']
            and nix['recursive_contents_verified'], 'STORE_VERIFICATION_REQUIRED')
    record = {'schema_version':1,'authority':'unverified-local-test-result',
        'production_access':False,'production_ready':False,'execution':execution,'result':result,
        'collector_status':collector,'payload_comparison':comparison,'nix':nix,
        'preparation_repeat':read(BASE/'complete-chain-preparation-repeat-20261031-01.json'),
        'runtime_sha256':sha(FIXTURE/'runtime.json'),'exercised_sources_sha256':runtime['code_sha256'],
        'fixture_launcher_revision':'bbe3df6f3ce0e5d3bc1ab6488314e243ab0fb4f7',
        'control_sources_sha256':{n:sha(ROOT/'operations/forgejo/tests'/n) for n in
            ['prepare_complete_chain.py','stage_complete_chain.py','launch_complete_chain.py',
             'verify_complete_chain_store.py','record_complete_chain.py']},
        'earlier_failures_preserved':[
            {'stage':'Nix evaluation of local expression','reason':'Pure --expr evaluation refused the absolute local path; corrected to explicit --file, without changing the derivation',
             'log_sha256':sha(BASE/'complete-chain-stage-20261031-01.log')},
            {'stage':'First integration','execution':read(BASE/'complete-chain-run-20261031-01/execution.json'),
             'diagnosis':read(BASE/'complete-chain-run-20261031-01/diagnosis.json'),
             'result_sha256':sha(BASE/'complete-chain-run-20261031-01/result.jsonl')}],
        'logs_sha256':{str(p.relative_to(BASE)):sha(p) for p in [RUN/'result.jsonl',RUN/'execution.json',
            RUN/'execution.log',BASE/'complete-chain-stage-20261031-02.json',
            BASE/'complete-chain-stage-20261031-03.json',BASE/'complete-chain-nix-verification-20261031-01.log']},
        'limits':['Entirely synthetic Forgejo/SQLite, identities and credentials; no production connection or native SSO/MFA',
            'Root socket listeners in offline disposable containers replace systemd activation; the NixOS service tests remain distinct',
            'Forgejo and runner share UID 65534 only in this fixture; collector and worker use distinct 59991 and 59990',
            'The rule commit is reproducible local public code, not protected production adoption or signing authority',
            'Existing Nix runtime artifacts and their original manifests remain selected; the new frontend transport archive retains its different provenance hash',
            'VPS reconciliation, quotas, secret references, coherent data migration, backup/restore and deployment/rollback controller still require qualification']}
    for path in [ROOT/'operations/forgejo/qualification-complete-chain-20261031.json',
                 VALIDATION/'operational-review/forgejo-complete-chain-pass-20261031.json']:
        with path.open('x') as out:
            out.write(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'decision':'recorded-passed-synthetic-complete-chain','integration_checks':17,
        'verifier_steps':len(verification['steps']),'identical_frontend_payload_files':442,'production_ready':False}))


if __name__ == '__main__':
    main()
