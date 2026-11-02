import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import boot_guard
import system_control as m
GUARD="/nix/store/"+"a"*32+"-synthetic-guard/bin/mrjam-first-cutover-guard"


class ServiceBoundaries(unittest.TestCase):
    def test_no_free_unit_accepted(self):
        control = m.SystemControl("/fixed/systemctl", "/fixed/nft", GUARD)
        for unit in ("sshd.service", "../../x", "other.timer"):
            with self.assertRaisesRegex(m.Refused, "UNIT_REFUSED"):
                control.properties(unit)

    def test_private_diagnostics_not_returned(self):
        control = m.SystemControl("/fixed/systemctl", "/fixed/nft", GUARD, run=lambda *a,**k: subprocess.CompletedProcess(a,1,b"PRIVATE",b"PRIVATE"))
        with self.assertRaisesRegex(m.Refused, "SYSTEM_OPERATION_REFUSED") as caught:
            control.execute(["/fixed/systemctl", "show"])
        self.assertNotIn("PRIVATE",str(caught.exception))

    def test_foreign_masks_preserved(self):
        control = m.SystemControl("/fixed/systemctl", "/fixed/nft", GUARD)
        control.foreign_masks={"forgejo.service"}
        control.masked_here={"nginx.service"}
        with patch.object(control, "execute") as execute,patch.object(control,"publish_masks") as publish:
            control.release_masks(["forgejo.service"])
            execute.assert_not_called()
            publish.assert_not_called()
        self.assertEqual(control.masked_here,{"nginx.service"})

    def test_still_stopping_postgresql_is_not_quiescent(self):
        control = m.SystemControl("/fixed/systemctl", "/fixed/nft", GUARD, clock=lambda:0, sleep=lambda _:None)
        with patch.object(control,"properties",return_value={"ActiveState":"deactivating", "MainPID":"0"}):
            with self.assertRaisesRegex(m.Refused,"WRITERS_NOT_QUIESCENT"):
                control.wait_stopped(["postgresql.service"],seconds=0)

    def test_output_limit_refused(self):
        control = m.SystemControl("/fixed/systemctl", "/fixed/nft", GUARD, run=lambda *a,**k: subprocess.CompletedProcess(a,0,b"x"*4097,b""))
        with self.assertRaisesRegex(m.Refused,"SYSTEM_RESULT_REFUSED"):
            control.execute(["/fixed/systemctl"],capture=True)

    def test_boot_holds_every_interrupted_phase(self):
        for phase in boot_guard.Phase:
            value={"schema_version":1,"phase":phase.value,"elapsed_seconds":10}
            with patch.object(boot_guard,"active_transaction",return_value=False), \
                    patch.object(boot_guard,"read_private",side_effect=[value,FileNotFoundError()]):
                expected=frozenset() if phase in (boot_guard.Phase.OPEN,boot_guard.Phase.RETURNED) else m.ALLOWED
                self.assertEqual(boot_guard.selected_masks(),expected)

    def test_reload_allowed_only_during_live_transaction(self):
        phase={"schema_version":1,"phase":"state-adopted","elapsed_seconds":1}
        masks={"schema_version":1,"units":["nginx.service"]}
        with patch.object(boot_guard,"active_transaction",return_value=True), \
                patch.object(boot_guard,"read_private",side_effect=[phase,masks]):
            self.assertEqual(boot_guard.selected_masks(),frozenset({"nginx.service"}))
        with patch.object(boot_guard,"active_transaction",return_value=True), \
                patch.object(boot_guard,"read_private",side_effect=[phase,FileNotFoundError()]):
            self.assertEqual(boot_guard.selected_masks(),m.ALLOWED)

    def test_terminal_phases_keep_remaining_masks_after_lease_exit(self):
        for phase in (boot_guard.Phase.OPEN,boot_guard.Phase.RETURNED):
            with patch.object(boot_guard,"active_transaction",return_value=False), \
                    patch.object(boot_guard,"read_private",side_effect=[
                        {"schema_version":1,"phase":phase,"elapsed_seconds":1},
                        {"schema_version":1,"units":["mrjam-adopt-matheval.service"]}]):
                self.assertEqual(boot_guard.selected_masks(),{"mrjam-adopt-matheval.service"})

    def test_malformed_masks_and_held_phase_remain_closed(self):
        for malformed in ({"schema_version":True,"units":[]},{"schema_version":1,"units":["sshd.service"]},
                          {"schema_version":1,"units":["nginx.service","nginx.service"]},
                          {"schema_version":1,"units":[{}]}):
            with patch.object(boot_guard,"active_transaction",return_value=True), \
                    patch.object(boot_guard,"read_private",side_effect=[
                        {"schema_version":1,"phase":"state-adopted","elapsed_seconds":1},malformed]):
                self.assertEqual(boot_guard.selected_masks(),m.ALLOWED)
        with patch.object(boot_guard,"active_transaction",return_value=True), \
                patch.object(boot_guard,"read_private",return_value={"schema_version":1,"phase":"held-for-recovery","elapsed_seconds":1}):
            self.assertEqual(boot_guard.selected_masks(),m.ALLOWED)

    def test_portable_guard_refuses_foreign_executable_or_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            control=m.SystemControl("/fixed/systemctl","/fixed/nft",GUARD,owner=os.getuid(),
                mask_directory=root/"state",generator_directory=root/"generators")
            before=os.umask(0o077)
            try:
                control.install_guard()
            finally:
                os.umask(before)
            self.assertEqual((root/"generators").stat().st_mode & 0o777,0o755)
            target=root/"generators"/m.GENERATOR_NAME
            self.assertEqual(os.readlink(target),GUARD)
            control.install_guard()
            target.unlink()
            target.symlink_to("/invented/foreign")
            with self.assertRaisesRegex(m.Refused,"FOREIGN_RUNTIME_GENERATOR_REFUSED"):
                control.install_guard()

    def test_mask_publication_is_private_and_unit_set_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            control=m.SystemControl("/fixed/systemctl","/fixed/nft",GUARD,owner=os.getuid(),
                mask_directory=root/"state",generator_directory=root/"generators")
            control.masked_here={"nginx.service","postgresql.service"}
            control.publish_masks()
            record=root/"state/masks.json"
            self.assertEqual(record.stat().st_mode & 0o777,0o600)
            self.assertEqual(json.loads(record.read_text()),{"schema_version":1,"units":["nginx.service","postgresql.service"]})
            control.masked_here={"sshd.service"}
            with self.assertRaisesRegex(m.Refused,"MASK_SET_REFUSED"):
                control.publish_masks()

    def test_ineffective_masks_are_not_accepted_as_a_freeze(self):
        control=m.SystemControl("/fixed/systemctl","/fixed/nft",GUARD)
        control.masked_here={"mrjam-rust-blue.service"}
        with patch.object(control,"properties",return_value={"LoadState":"loaded"}):
            with self.assertRaisesRegex(m.Refused,"EARLY_MASK_NOT_EFFECTIVE"):
                control.verify_masks()


if __name__ == "__main__":
    unittest.main()
