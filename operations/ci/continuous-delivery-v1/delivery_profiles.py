"""Installed repository identities select a delivery profile, never PR fields.

Selecting a profile grants no admission or deployment permission. A missing
profile implementation remains a refusal, independent of other queued jobs.
"""
from source_snapshot import require

REPOSITORIES = {
    'Signature': (1374156543, 'platform'),
    'apprendre-a-demontrer': (1371197112, 'platform'),
    'etp-vie-affective': (1433178398, 'vise'),
    'matheval': (1437121919, 'platform'),
    'mrjam-plateforme': (1437120781, 'platform'),
    'style-mrjam': (1379878757, 'platform'),
    'vision': (1354721741, 'platform'),
}


def selected(proposal):
    require(type(proposal) is dict and type(proposal.get('repository')) is str,
            'DELIVERY_PROFILE_PROPOSAL_REFUSED')
    identity = REPOSITORIES.get(proposal['repository'])
    require(identity is not None, 'PROJECT_RECIPE_UNAVAILABLE')
    require(type(proposal.get('repository_id')) is int and proposal['repository_id']==identity[0],
            'DELIVERY_PROFILE_REPOSITORY_REFUSED')
    return identity[1]
