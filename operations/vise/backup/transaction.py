"""Coherent offline capture with durable restart intent.

The fixed adapter holds the deployment lock throughout this transaction. It
captures database plus deletion ledger only after proving the writer offline.
No restoration is performed. Recovery never resumes an interrupted capture:
it restores availability, leaving incomplete private files for reconciliation.
"""


def require(value, code):
    if not value:
        raise RuntimeError(code)


PHASES = {'quiescing', 'offline', 'captured', 'published', 'complete', 'aborted'}


def checked(value):
    require(type(value) is dict and set(value) == {
        'schema_version', 'phase', 'restart_required', 'capture_id'
    }, 'VISE_BACKUP_JOURNAL_REFUSED')
    require(type(value['schema_version']) is int and value['schema_version'] == 1
            and value['phase'] in PHASES
            and type(value['restart_required']) is bool
            and type(value['capture_id']) is str
            and len(value['capture_id']) == 32
            and all(c in '0123456789abcdef' for c in value['capture_id']),
            'VISE_BACKUP_JOURNAL_REFUSED')
    return dict(value)


def recover(adapter):
    """Also called by the unit's fixed ExecStopPost after termination."""
    previous = adapter.read()
    if previous is None:
        return 'VISE_BACKUP_NO_RECOVERY'
    value = checked(previous)
    if value['phase'] in {'complete', 'aborted'}:
        return 'VISE_BACKUP_RECOVERY_COMPLETE'
    # Intent precedes stop, so loss of the stop acknowledgement cannot leave
    # a previously running service offline. Start is idempotent; verify it.
    if value['restart_required']:
        adapter.start()
        adapter.ready()
    value['phase'] = 'complete' if value['phase'] == 'published' else 'aborted'
    adapter.save(value)
    return 'VISE_BACKUP_RECOVERED'


def capture(adapter):
    previous = adapter.read()
    if previous is not None:
        value = checked(previous)
        if value['phase'] not in {'complete', 'aborted'}:
            return recover(adapter)
    adapter.preflight()
    value = checked({'schema_version': 1, 'phase': 'quiescing',
                     'restart_required': adapter.active(),
                     'capture_id': adapter.identifier()})
    adapter.save(value)
    try:
        adapter.stop()
        adapter.offline()
        value['phase'] = 'offline'
        adapter.save(value)
        adapter.capture(value['capture_id'])
        adapter.offline()
        adapter.verify(value['capture_id'])
        value['phase'] = 'captured'
        adapter.save(value)
        # Publication must be exclusive, atomic and fsynced. A crash after
        # publication but before acknowledgement may retain a valid backup;
        # recovery never overwrites it or claims it as a completed run.
        adapter.publish(value['capture_id'])
        value['phase'] = 'published'
        adapter.save(value)
    except Exception:
        recover(adapter)
        raise
    recover(adapter)
    return 'VISE_BACKUP_COMPLETE'
