"""The three Cloud findings, asserted as corrected behavior on the candidate."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from coordinator_cases import Fixture, PowerCut, D, S, M, json


def legacy(f):
    f.previousB.pop('format', None)
    f.previousB.pop('rollback', None)
    D.atomic_json(f.state / 'current.json', f.previousB)
    baseline = json.loads((f.state / 'baseline.json').read_text())
    baseline['nginx'] = f.manifest['nginx'] + '/bin/nginx'
    D.atomic_json(f.state / 'baseline.json', baseline)
    original_read, original_link = Path.read_text, D.symlink

    def read(path, *args, **kwargs):
        if str(path) == f.manifest['server'] + '/share/mrjam/source-revision':
            return 'c' * 40
        return original_read(path, *args, **kwargs)

    def link(target, path):
        if str(path).startswith('/nix/var/nix/gcroots/'):
            return
        return original_link(target, path)

    for item in [patch.object(Path, 'read_text', read),
                 patch.object(D, 'symlink', side_effect=link),
                 patch.object(D, 'candidate_configuration', return_value='/nix/store/' + 'c' * 32 + '-runtime/runtime.json'),
                 patch.object(D, 'public_check', return_value=None)]:
        f.stack.enter_context(item)
    return {'revision': 'c' * 40, 'output': f.manifest['server'], 'schema_digest': 's'}


class LegacySlotRegression(unittest.TestCase):
    def test_original_ABC_failed_preparation_then_rollback_B_keeps_A(self):
        with Fixture() as f:
            build = legacy(f)
            ticks = iter([0, 31])
            with patch.object(D, 'probe', side_effect=lambda slot, *args: slot == 'green'), \
                    patch.object(D.time, 'monotonic', side_effect=lambda: next(ticks)):
                with self.assertRaises(RuntimeError):
                    D.promote(build)
            self.assertEqual(f.running, {'blue': f.exec['A'], 'green': f.exec['B']})
            D.rollback({'revision': 'b' * 40, 'old_configuration': str(f.confA), 'old_state': f.previousA})
            self.assertEqual(f.route.resolve(), f.confA)
            self.assertEqual(f.running['blue'], f.exec['A'])

    def test_interrupted_legacy_rollback_keeps_journal_until_slot_restored(self):
        with Fixture() as f:
            D.promote(legacy(f))
            current = json.loads((f.state / 'current.json').read_text())
            transaction = {'revision': 'c' * 40, 'old_configuration': str(f.confB),
                           'old_state': f.previousB, 'replaced_slot': current['replaced_slot']}
            with patch.object(D, 'configure_slot', side_effect=PowerCut('interrupt displaced-slot restoration')):
                with self.assertRaises(PowerCut):
                    D.rollback(transaction)
            self.assertTrue((f.state / 'transaction.json').exists())
            D.recover()
            self.assertFalse((f.state / 'transaction.json').exists())
            self.assertEqual(f.running['blue'], f.exec['A'])
            D.rollback({'revision': 'b' * 40, 'old_configuration': str(f.confA), 'old_state': f.previousA})
            self.assertEqual(f.route.resolve(), f.confA)
            self.assertEqual(f.running['blue'], f.exec['A'])


@unittest.skipUnless(os.environ.get('MRJAM_TEST_MIGRATION_PROGRAM'), 'Nix migration-program fixture required')
class HeldServiceRegression(unittest.TestCase):
    def check_held_service(self, unit, was_active):
        with Fixture() as f, patch.dict(os.environ, MRJAM_MIGRATION_FIXTURE=str(f.root)):
            (f.root / '.synthetic').touch()
            (f.root / 'fail_verify').touch()
            for suffix in ['B', 'C']:
                target = f.packages['system-' + suffix] / 'etc/systemd/system' / (unit + '.service')
                if not target.exists():
                    target.write_text('[Service]\nExecStart=synthetic-unchanged\n')
            plan = {'version': 1, 'steps': [{'id': 'synthetic_held', 'driver': 'program', 'scope': 'server',
                    'compatibility': 'maintenance', 'package': os.environ['MRJAM_TEST_MIGRATION_PROGRAM'],
                    'hold_units': [unit]}]}
            (f.packages['release-C'] / 'migrations/plan.json').write_text(json.dumps(plan))
            active = {unit: was_active}
            original = f.command

            def command(args, **kwargs):
                if args[:2] == ['systemctl', 'show'] and args[2] == unit + '.service':
                    return 'active' if active[unit] else 'inactive'
                if args[:2] == ['systemctl', 'stop'] and unit + '.service' in args[2:]:
                    active[unit] = False
                if args[:2] in [['systemctl', 'start'], ['systemctl', 'restart']] and unit + '.service' in args[2:]:
                    active[unit] = True
                return original(args, **kwargs)

            with patch.object(D, 'command', side_effect=command):
                with self.assertRaises(Exception):
                    S.promote(f.build)
                f.restoredB(self)
            self.assertEqual(active[unit], was_active)
            self.assertFalse((f.control / (unit + '.service.d') / '11-delivery-migration-hold.conf').exists())
            self.assertFalse((f.state / 'transaction.json').exists())
            self.assertNotIn('activation-enter', f.events)

    def test_postgresql_active_before_failure_is_started_again(self):
        self.check_held_service('postgresql', True)

    def test_previously_inactive_postgresql_is_not_started(self):
        self.check_held_service('postgresql', False)

    def test_active_held_service_outside_managed_list_is_started_again(self):
        self.check_held_service('synthetic-worker', True)
