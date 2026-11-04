"""Extend the previously protected platform checks, never a candidate report."""
FRONTENDS = ('audition', 'log', 'logique', 'mateval', 'style', 'style-logo', 'vision')


def extend(previous):
    steps = [name for name in previous if name != 'rust-reviewed-readiness-overlay']
    if len(steps) != 74 or len(set(steps)) != 74:
        raise ValueError('SIGNATURE_BASELINE_STEPS_CHANGED')
    additions = {'elm-rules-208': 'signature-resource-regeneration'}
    additions.update({'frontend-resource-closure-' + name:
                      'signature-resource-assembly-' + name for name in FRONTENDS})
    if not set(additions).issubset(steps) or any(name.startswith('signature-') for name in steps):
        raise ValueError('SIGNATURE_BASELINE_ANCHORS_CHANGED')
    result = []
    for name in steps:
        if name in additions:
            result.append(additions[name])
        result.append(name)
    assert len(result) == 82 and len(set(result)) == 82
    return result
