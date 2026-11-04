"""Bind the four protected acceptance receipts; no deployment authority."""
import contract as C,acceptance_pipeline as A,acceptance_commit as K

def checked(stage,job,ledger):
    A.checked(ledger,job)
    C.require(job['phase']=='validated' and job.get('promotion') is None
        and K.identity(job)=={k:stage[k] for k in ('schema_version','job','proposal_sha256','base_sha256')},
        'ENQUEUE_JOB_REFUSED')
    receipts=ledger['receipts']
    C.require(set(receipts)==set(A.STAGES) and ledger['inflight'] is None,'ENQUEUE_ACCEPTANCE_INCOMPLETE')
    proposal=job['capture']['proposal'];number=receipts['mirror'].get('number')
    C.require(type(number) is int and number>0,'ENQUEUE_PULL_REFUSED')
    for name,receipt in receipts.items():
        C.require(receipt.get('repository')==proposal['repository'] and receipt.get('head')==proposal['head'],
            'ENQUEUE_SOURCE_RECEIPT_CHANGED')
        if name!='sync':
            C.require(receipt.get('number')==number and receipt.get('proposal_sha256')==stage['proposal_sha256'],
                'ENQUEUE_ACCEPTANCE_RECEIPT_CHANGED')
    merged=receipts['merge'];synced=receipts['sync']
    C.require(merged.get('protected_fast_forward') is True and merged.get('merger')=='mrjam-release-merge'
        and type(receipts['review'].get('review_id')) is int and receipts['review']['review_id']>0
        and merged.get('review_id')==receipts['review'].get('review_id'),'ENQUEUE_MERGE_REFUSED')
    C.require(all(synced.get(k) is True for k in ('canonical_forgejo_main','github_main_synchronized','token_revoked')),
        'ENQUEUE_SYNC_REFUSED')
    return number,receipts['review']
