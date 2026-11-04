"""Bind the installed delivery stack to every executable that implements it.

The caller reads the descriptor from the protected system generation, never a
proposal. This verifies configuration consistency, not permission to deploy.
"""
import re
import generation_views as G
from source_snapshot import require

COMMANDS={
    'admission': {'mrjam-admission-controller.service':'mrjam-admission-controller'},
    'anchor': {
        'mrjam-validation-worker@.service':'mrjam-validation-bound-worker',
        'mrjam-validation-collector@.service':'mrjam-validation-bound-collector',
        'mrjam-validation-export@.service':'mrjam-validation-export',
        'mrjam-validation-authority.service':'mrjam-validation-attest'},
    'acceptance': {'mrjam-acceptance-'+s+'.service':'mrjam-acceptance-'+s
        for s in ('mirror','review','merge','sync')},
    'preparation': {'mrjam-delivery-preparation.service':'mrjam-delivery-prepare'},
    'staging': {'mrjam-delivery-staging.service':'mrjam-delivery-stage'},
    'promotion': {'mrjam-promotion.service':'mrjam-promotion'},
}
UNITS=tuple(unit for commands in COMMANDS.values() for unit in commands)

def verify(descriptor, units, control):
    require(type(descriptor) is dict and set(descriptor)=={
        'schema_version','deployment_authorized','enableVise','packages'}
        and type(descriptor['schema_version']) is int and descriptor['schema_version']==1
        and descriptor['deployment_authorized'] is False
        and type(descriptor['enableVise']) is bool,'DELIVERY_STACK_DESCRIPTOR_REFUSED')
    packages=descriptor['packages']
    require(type(packages) is dict and set(packages)==set(COMMANDS)
        and all(G.store(p) for p in packages.values()),'DELIVERY_STACK_PACKAGES_REFUSED')
    require(type(control) is dict and set(control)=={'preparation','acceptance','staging'}
        and all(packages[name]==path for name,path in control.items()),'DELIVERY_STACK_CONTROL_REFUSED')
    for name, commands in COMMANDS.items():
        for unit, executable in commands.items():
            raw=units.get(unit,'')
            starts=re.findall(r'^ExecStart=(.*)$',raw,re.M)
            require(starts==[packages[name]+'/bin/'+executable], 'DELIVERY_STACK_UNIT_REFUSED')
    conditions=re.findall(r'^ConditionPathExists=(.*)$',units['mrjam-promotion.service'],re.M)
    require(conditions==([] if descriptor['enableVise'] else ['/var/lib/mrjam-promotion/plan.json']),
        'DELIVERY_STACK_QUEUE_MODE_REFUSED')
    return packages
