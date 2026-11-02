"""Independent fault-boundary review: disposable metadata, no service operation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cutover
import recovery
import release_backend


class PowerLoss(BaseException):
    pass


class InterruptedEarlyReturn:
    def __init__(self):
        self.calls = []
        self.first_freeze = True
        self.interrupt_return = True

    def freeze(self):
        self.calls.append('freeze')
        if self.first_freeze:
            self.first_freeze = False
            raise RuntimeError('invented pre-snapshot failure')

    def restore_previous_generation(self):
        self.calls.append('restore_previous_generation')
        if self.interrupt_return:
            self.interrupt_return = False
            raise PowerLoss()

    def adoption_started(self):
        self.calls.append('adoption_started')
        return False

    def verify_snapshot(self):
        raise AssertionError('No snapshot was created; recovery must not require one')

    def restore_snapshot(self):
        raise AssertionError('No snapshot exists to extract')

    def __getattr__(self, name):
        def action():
            self.calls.append(name)
        return action


class IndependentBoundaryTests(unittest.TestCase):
    def test_power_loss_during_early_return_recovers_without_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = cutover.Checkpoint(directory, uid=os.getuid())
            backend = InterruptedEarlyReturn()
            with self.assertRaises(PowerLoss):
                cutover.Cutover(backend, checkpoint).execute()
            self.assertEqual(checkpoint.read(), cutover.Phase.RETURNING)
            self.assertNotIn('snapshot', backend.calls)
            result = recovery.recover_before_opening(backend, checkpoint)
            self.assertEqual(result['phase'], cutover.Phase.RETURNED.value)
            self.assertIn('verify_adoption_not_started', backend.calls)
            self.assertLess(backend.calls.index('adoption_started'), backend.calls.index('reopen_previous_services'))

    def test_periodic_old_services_wait_for_returned_not_only_their_timers(self):
        backend = object.__new__(release_backend.Backend)
        backend.clock, backend.started, backend.sleep = time.monotonic, None, time.sleep
        phase = cutover.Phase.RETURNING
        backend.checkpoint = SimpleNamespace(read=lambda:phase)
        periodic = {'vision-cycle.service','mrjam-courriel.service','nextcloud-cron.service'}
        starts, released, boot = [], [], []
        backend.control = SimpleNamespace(active_before=periodic | {'nginx.service','postgresql.service'},
            release_masks=lambda units:released.extend(units), start=lambda units:starts.extend(units),
            open_ingress=lambda:None)
        backend.original = {'foreign_masks':[], 'http_status':{host:200 for host in release_backend.DOMAINS}}
        backend.previous_http = lambda:backend.original['http_status']
        backend.generations = SimpleNamespace(previous='invented-old',select_boot=lambda target:boot.append(target))
        backend.verify_previous_private_services()
        self.assertFalse(periodic & set(released), 'Periodic services were unmasked before RETURNED')
        self.assertFalse(periodic & set(starts), 'Periodic services were restarted before RETURNED')
        self.assertEqual(set(starts), {'nginx.service','postgresql.service'})
        phase = cutover.Phase.RETURNED
        backend.reopen_previous_services()
        self.assertLessEqual(periodic, set(starts))
        self.assertEqual(boot, ['invented-old'])

    def test_opening_or_returned_refuses_both_real_restore_methods(self):
        backend = object.__new__(release_backend.Backend)
        for phase in (cutover.Phase.OPENING,cutover.Phase.OPEN,cutover.Phase.RETURNED,cutover.Phase.HELD):
            backend.checkpoint = SimpleNamespace(read=lambda:phase)
            for method in (backend.restore_snapshot,backend.restore_previous_generation):
                with self.subTest(phase=phase,method=method.__name__), self.assertRaises(release_backend.Refused):
                    method()

    def test_registered_hash_command_works_with_nix_command_disabled_in_config(self):
        nix = shutil.which('nix')
        if not nix:
            self.skipTest('Nix unavailable in this test environment')
        root = str(Path(nix).resolve().parent.parent)
        probe = subprocess.run([nix,'--extra-experimental-features','nix-command','path-info','--json',root],
            capture_output=True, check=True)
        info = json.loads(probe.stdout)
        if isinstance(info,list):
            digest = info[0]['narHash']
        else:
            digest = info[root]['narHash']
        backend = object.__new__(release_backend.Backend)
        backend.release = SimpleNamespace(roots={root},artifacts={root:digest},tools={'nix':nix,'nix_store':'invented-nix-store'})
        invoked = []
        def command(argv,**_):
            if '--requisites' in argv:
                return (root+'\n').encode()
            if '--verify-path' in argv:
                return None
            invoked.append(argv)
            # The old host need not enable experimental features globally.
            result = subprocess.run([argv[0],'--option','experimental-features','',*argv[1:]],
                capture_output=True,check=False,timeout=15)
            self.assertEqual(result.returncode,0,'Explicit nix-command was missing from the sealed backend invocation')
            return result.stdout
        backend.command = command
        backend.verify_artifacts()
        self.assertEqual(len(invoked),1)

    def test_initial_without_phase_requires_same_release_and_no_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            state, volatile, generators = (base/name for name in ('state','volatile','generators'))
            for path in (state,volatile,generators):
                path.mkdir(mode=0o700)
            backend = object.__new__(release_backend.Backend)
            backend.release = SimpleNamespace(digest='a'*64,tools={'nft':'invented-nft'})
            observations = []
            backend.generations = SimpleNamespace(verify_previous=lambda:observations.append('old-current-and-boot'))
            backend.control = SimpleNamespace(execute=lambda *_a,**_k:1)
            document = {'schema_version':1,'release_sha256':'a'*64,'active_units':[], 'foreign_masks':[],
                'runtime_mask_intent':sorted(release_backend.ALLOWED),'http_status':{host:200 for host in release_backend.DOMAINS}}
            (state/'initial.json').write_text(json.dumps(document))
            # Ownership is covered by helper tests/VM. This independent test
            # isolates the durable-state decision using real temporary files.
            with patch.object(release_backend,'STATE',state), patch.object(release_backend,'VOLATILE',volatile), \
                 patch.object(release_backend,'GENERATOR_DIRECTORY',generators), \
                 patch.object(release_backend,'private_read',side_effect=lambda path,**_:json.loads(path.read_bytes())):
                self.assertTrue(backend.prepare_preflight_retry())
                self.assertEqual(observations,['old-current-and-boot'])
                document['release_sha256'] = 'b'*64
                (state/'initial.json').write_text(json.dumps(document))
                with self.assertRaises(release_backend.Refused):
                    backend.prepare_preflight_retry()
                document['release_sha256'] = 'a'*64
                (state/'initial.json').write_text(json.dumps(document))
                for name in ('phase.json','adoption-started.json'):
                    (state/name).write_text('{}')
                    with self.assertRaises(release_backend.Refused):
                        backend.prepare_preflight_retry()
                    (state/name).unlink()
                (volatile/'masks.json').write_text('{}')
                with self.assertRaises(release_backend.Refused):
                    backend.prepare_preflight_retry()
                self.assertTrue((state/'initial.json').exists())


if __name__ == '__main__':
    unittest.main()
