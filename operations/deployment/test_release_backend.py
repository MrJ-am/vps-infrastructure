"""Invented release metadata and injected operations; no production access."""
import copy
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import release_backend as m
from cutover import Phase


def invented(name):
    return "/nix/store/" + "a"*32 + "-invented-" + name


def manifest():
    value={"schema_version":1,"target":m.HOST,
           "generations":{"previous":m.PREVIOUS,"staged":invented("staged"),"promoted":invented("promoted")},
           "tools":{key:invented(key)+suffix for key,suffix in m.TOOLS.items()},
           "helpers":{key:invented(key)+suffix for key,suffix in m.HELPERS.items()},
           "ca_file":invented("ca")+"/ca.pem","forgejo_binding_sha256":"0"*64,
           "generator":invented("guard")+"/bin/mrjam-first-cutover-guard"}
    roots=set(value["generations"].values())|{invented(key) for key in m.TOOLS}|{invented(key) for key in m.HELPERS}|{invented("ca"),invented("guard")}
    value["artifacts"]={path:"sha256-"+"A"*43+"=" for path in roots}
    return value


def sealed(value=None):
    raw=json.dumps(manifest() if value is None else value).encode()
    return m.Release(raw,hashlib.sha256(raw).hexdigest())


class Control:
    def __init__(self,trace):
        self.trace=trace
        self.active_before={"nginx.service","postgresql.service","mrjam-vision-cycle.timer"}
        self.masked_here=set()
        self.observed=True
        self.gate_created=False

    def execute(self,argv,**kwargs):
        self.trace.append(("execute",tuple(argv)))
        return 1

    def properties(self,unit):
        return {"LoadState":"loaded","ActiveState":"active" if unit in m.PRIVATE_SERVICES else "inactive"}

    def __getattr__(self,name):
        def call(*args,**kwargs):
            self.trace.append((name,*args))
        return call


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.trace=[]
        self.phase=Phase.PREPARED
        self.now=1000
        self.backend=m.Backend(sealed(),run=lambda *_a,**_k: self.fail("unexpected executable"),clock=lambda:self.now)
        self.backend.control=Control(self.trace)
        original=self.backend.generations
        self.backend.generations=SimpleNamespace(previous=original.previous,staged=original.staged,promoted=original.promoted,
            select_boot=lambda target:self.trace.append(("boot",target)),
            activate=lambda target:self.trace.append(("activate",target)),
            verify_paths=lambda:self.trace.append(("verify_paths",)),
            verify_previous=lambda:self.trace.append(("verify_previous",)))
        self.backend.checkpoint=SimpleNamespace(read=lambda:self.phase)
        self.backend.original={"foreign_masks":[],"http_status":{host:200 for host in m.DOMAINS}}
        self.backend.lock=123

    def test_inventory_only_contains_closed_control_units(self):
        for group in (m.FILE_ADOPTIONS,m.SQL_ADOPTIONS,m.PRIVATE_SERVICES,m.PUBLIC_TIMERS,m.TIMER_SERVICES):
            self.assertLessEqual(set(group),m.ALLOWED)
        self.assertLessEqual(m.RETURN_DELAYED,m.ALLOWED)

    def test_complete_closure_and_bytes_are_both_verified(self):
        def command(argv,**_):
            self.trace.append(tuple(argv))
            if "--requisites" in argv:
                return ("\n".join(sorted(self.backend.release.artifacts))+"\n").encode()
            if "path-info" in argv:
                self.assertEqual(argv[1:3],["--extra-experimental-features","nix-command"])
                return json.dumps({path:{"narHash":self.backend.release.artifacts[path]} for path in argv[5:]}).encode()
        self.backend.command=command
        self.backend.verify_artifacts()
        self.assertTrue(any("--verify-path" in call for call in self.trace))
        self.assertTrue(any("path-info" in call for call in self.trace))
        self.assertIn("--requisites",self.trace[0])

    def test_missing_transitive_path_refuses_before_registered_hash_trust(self):
        self.backend.command=lambda *_a,**_k:("\n".join(self.backend.release.artifacts)+"\n"+invented("not-sealed")+"\n").encode()
        with self.assertRaisesRegex(m.Refused,"ARTIFACT_CLOSURE_CHANGED"):
            self.backend.verify_artifacts()

    def test_both_generations_must_embed_the_portable_guard_exactly(self):
        with patch.object(m.os.path,"realpath",return_value=self.backend.release.generator):
            self.backend.verify_guard_binding()
        with patch.object(m.os.path,"realpath",return_value=invented("other-guard")+"/bin/mrjam-first-cutover-guard"), \
                self.assertRaisesRegex(m.Refused,"GENERATION_GUARD_BINDING_CHANGED"):
            self.backend.verify_guard_binding()

    def test_staged_boot_is_selected_before_any_freeze(self):
        self.backend.arm_deadline=lambda:None
        self.backend.freeze()
        self.assertEqual(self.trace[:2],[("boot",self.backend.generations.staged),("freeze",)])
        self.backend.freeze()
        self.assertEqual(sum(call[0]=="boot" for call in self.trace),1)

    def test_activation_intent_is_durable_first_and_gate_reclosed_on_failure(self):
        self.phase=Phase.SNAPSHOT
        def activate(target):
            self.trace.append(("activate",target))
            raise RuntimeError("invented activation failure")
        self.backend.generations.activate=activate
        with patch.object(m,"publish_private",side_effect=lambda path,value:self.trace.append(("durable",path.name))), \
                self.assertRaises(RuntimeError):
            self.backend.install_candidate()
        self.assertEqual([call[0] for call in self.trace],["durable","activate","close_ingress"])

    def test_no_activation_without_snapshot_checkpoint(self):
        for phase in (Phase.FROZEN,Phase.OPENING,Phase.OPEN,Phase.RETURNING,Phase.RETURNED):
            self.phase=phase
            with self.assertRaisesRegex(m.Refused,"SNAPSHOT_CHECKPOINT_REQUIRED"):
                self.backend.install_candidate()
        self.assertEqual(self.trace,[])

    def test_private_adoption_prepares_images_and_migrates_schema_before_role(self):
        self.phase=Phase.CANDIDATE
        self.backend.verify_obligations=lambda:self.trace.append(("obligations",))
        with patch.object(m.stage_credentials,"prepare",side_effect=lambda:self.trace.append(("stage_credentials",))), \
                patch.object(m.stage_adoption,"prepare",side_effect=lambda:self.trace.append(("stage_sqlite",))):
            self.backend.adopt_private_state()
        starts=[call[1] for call in self.trace if call[0]=="start"]
        self.assertEqual(starts[0],m.FILE_ADOPTIONS)
        self.assertEqual(starts[1],("postgresql.service",))
        self.assertEqual(starts[2],m.SQL_ADOPTIONS)
        self.assertLess(starts[2].index("mrjam-upgrade-forgejo-schema.service"),starts[2].index("mrjam-adopt-forgejo-role.service"))
        self.assertLess([call[0] for call in self.trace].index("stage_sqlite"),[call[0] for call in self.trace].index("start"))
        self.assertFalse(set(sum(starts,()))&set(m.PUBLIC_TIMERS))

    def test_real_governance_attestation_is_required_before_private_success(self):
        self.phase=Phase.ADOPTED
        self.backend.helper=lambda name: ({"technical_account_eligible":True,"technical_account_attested":True,
            "api_admin":True,"temporary_token_revoked":True} if name=="forgejo_probe" else
            {"schema_version":1,"binding_sha256":"f"*64,"sources_bound":True,
             "protected_policy_verified":True,"temporary_credentials_revoked":True})
        with self.assertRaisesRegex(m.Refused,"FORGEJO_RELEASE_AUTHORITY_NOT_ESTABLISHED"):
            self.backend.start_private_services()
        self.assertFalse(any(set(call[1])&set(m.PUBLIC_TIMERS) for call in self.trace if call[0]=="start"))

    def test_public_open_refuses_every_other_phase_without_effect(self):
        for phase in Phase:
            if phase==Phase.OPENING:
                continue
            self.phase=phase
            with self.assertRaisesRegex(m.Refused,"DURABLE_OPENING_REQUIRED"):
                self.backend.open_public_writes()
        self.assertEqual(self.trace,[])

    def test_promoted_boot_activation_writers_then_ingress(self):
        self.phase=Phase.OPENING
        self.backend.open_public_writes()
        self.assertEqual(self.trace[0],("boot",self.backend.generations.promoted))
        self.assertEqual(self.trace[1],("activate",self.backend.generations.promoted))
        self.assertEqual(self.trace[2],("close_ingress",))
        self.assertEqual(self.trace[-2:],[("start",m.PUBLIC_TIMERS),("open_ingress",)])
        self.assertLess(self.trace.index(("stop",("mrjam-vision-admission.service",))),self.trace.index(("start",m.PRIVATE_SERVICES)))

    def test_old_running_generation_keeps_guarded_boot_during_returning(self):
        self.phase=Phase.RETURNING
        self.backend.restore_previous_generation()
        self.assertEqual(self.trace,[("activate",self.backend.generations.previous),("close_ingress",)])
        with self.assertRaisesRegex(m.Refused,"DURABLE_RETURNED_REQUIRED"):
            self.backend.reopen_previous_services()
        self.phase=Phase.RETURNED
        self.backend.reopen_previous_services()
        self.assertEqual(self.trace[2],("boot",self.backend.generations.previous))
        self.assertEqual(self.trace[-1],("open_ingress",))

    def test_neither_old_restore_nor_snapshot_restore_can_cross_open_boundary(self):
        self.backend.saved=SimpleNamespace(restore=lambda:self.fail("snapshot restored"))
        for phase in (Phase.OPENING,Phase.OPEN,Phase.RETURNED,Phase.HELD):
            self.phase=phase
            for operation in (self.backend.restore_snapshot,self.backend.restore_previous_generation):
                with self.assertRaisesRegex(m.Refused,"RETURN_CHECKPOINT_REQUIRED"):
                    operation()
        self.assertEqual(self.trace,[])

    def test_previous_verification_does_not_remove_foreign_masks_or_start_timers(self):
        self.phase=Phase.RETURNING
        foreign="vise.service"
        self.backend.original["foreign_masks"]=[foreign]
        self.backend.previous_http=lambda:self.backend.original["http_status"]
        self.backend.verify_previous_private_services()
        released=self.trace[0][1]
        self.assertNotIn(foreign,released)
        self.assertFalse(set(released)&set(m.TIMERS))
        self.assertFalse(set(released)&{name+".service" for name in m.BACKUPS})
        started=sum([call[1] for call in self.trace if call[0]=="start"],())
        self.assertEqual(started,("postgresql.service","nginx.service"))

    def test_periodic_service_running_before_cutover_restarts_only_after_returned(self):
        periodic={"vision-cycle.service","nextcloud-cron.service","mrjam-courriel.service","acme-log.mrj.am.service"}
        self.backend.control.active_before |= periodic
        self.phase=Phase.RETURNING
        self.backend.previous_http=lambda:self.backend.original["http_status"]
        self.backend.verify_previous_private_services()
        released=self.trace[0][1]
        started=set(sum([call[1] for call in self.trace if call[0]=="start"],()))
        self.assertFalse(periodic&set(released));self.assertFalse(periodic&started)
        self.trace.clear();self.phase=Phase.RETURNED
        self.backend.reopen_previous_services()
        started=set(sum([call[1] for call in self.trace if call[0]=="start"],()))
        self.assertLessEqual(periodic,started)

    def test_adoption_marker_is_exact_and_bound_with_no_error_fallback(self):
        with patch.object(m.Path,"exists",return_value=False),patch.object(m.Path,"is_symlink",return_value=False):
            self.assertFalse(self.backend.adoption_started())
        good={"schema_version":1,"release_sha256":self.backend.release.digest}
        with patch.object(m.Path,"exists",return_value=True):
            with patch.object(m,"private_read",return_value=good):self.assertTrue(self.backend.adoption_started())
            for value in ({},dict(good,schema_version=True),dict(good,release_sha256="f"*64),dict(good,extra=True)):
                with patch.object(m,"private_read",return_value=value),self.assertRaisesRegex(m.Refused,"ADOPTION_MARKER_REFUSED"):
                    self.backend.adoption_started()
            with patch.object(m,"private_read",side_effect=m.Refused("PRIVATE_FILE_REFUSED")),self.assertRaises(m.Refused):
                self.backend.adoption_started()

    def test_remaining_budget_preserves_return_margin_and_bounds_process_timeout(self):
        self.backend.started=0
        self.now=5390
        self.assertEqual(self.backend.remaining(),10)
        self.backend.run=lambda argv,**kwargs:self.trace.append(kwargs["timeout"])
        self.backend.timed_run(["invented"],timeout=900)
        self.assertEqual(self.trace,[10])
        self.now=5400
        with self.assertRaisesRegex(m.Refused,"TIME_BUDGET_EXHAUSTED"):
            self.backend.remaining()
        self.phase=Phase.RETURNING
        self.assertEqual(self.backend.remaining(),5400)
        self.phase=Phase.RETURNED
        self.assertEqual(self.backend.remaining(),5400)
        self.now=10800
        with self.assertRaisesRegex(m.Refused,"TIME_BUDGET_EXHAUSTED"):
            self.backend.remaining()

    def test_failed_old_reopening_preserves_state_with_guarded_next_boot(self):
        self.phase=Phase.RETURNED
        with patch.object(m.os.path,"realpath",return_value=self.backend.generations.previous), \
                patch.object(m.signal,"setitimer"):
            self.backend.hold_current_state()
        self.assertEqual(self.trace,[("freeze",),("boot",self.backend.generations.staged)])

    def test_old_http_baseline_may_include_the_broken_route_being_repaired(self):
        self.backend.closed_status=lambda host:404 if host=="principiipetit.io" else 200
        baseline=self.backend.previous_http()
        self.assertEqual(baseline["principiipetit.io"],404)

    def http_retry_clock(self):
        self.phase=Phase.RETURNING
        def sleep(delay):
            self.trace.append(("sleep",delay))
            self.now+=delay
        self.backend.sleep=sleep

    def test_return_waits_for_transport_then_requires_exact_original_http(self):
        self.http_retry_clock()
        original=dict(self.backend.original["http_status"],**{"principiipetit.io":404})
        self.backend.original["http_status"]=original
        with patch.object(self.backend,"previous_http",side_effect=[m.Refused("SEALED_OPERATION_REFUSED"),original]) as observe:
            self.backend.verify_previous_private_services()
        self.assertEqual(observe.call_count,2)
        self.assertEqual([x for x in self.trace if x[0]=="sleep"],[("sleep",0.25)])
        self.assertNotIn("open_ingress",[x[0] for x in self.trace])
        self.assertFalse(set(sum([x[1] for x in self.trace if x[0]=="start"],()))&m.RETURN_DELAYED)

    def test_return_http_received_mismatch_is_not_retried_or_accepted(self):
        self.http_retry_clock()
        changed=dict(self.backend.original["http_status"],**{"forge.mrj.am":503})
        with patch.object(self.backend,"previous_http",return_value=changed) as observe, \
                self.assertRaisesRegex(m.Refused,"PREVIOUS_PRIVATE_HTTP_NOT_RESTORED"):
            self.backend.wait_previous_http()
        self.assertEqual(observe.call_count,1)
        self.assertEqual(self.trace,[])

    def test_return_http_connection_retry_window_is_bounded(self):
        self.http_retry_clock()
        with patch.object(self.backend,"previous_http",side_effect=m.Refused("SEALED_OPERATION_REFUSED")) as observe, \
                self.assertRaisesRegex(m.Refused,"PREVIOUS_PRIVATE_HTTP_NOT_RESTORED"):
            self.backend.wait_previous_http()
        self.assertEqual(observe.call_count,120)
        self.assertEqual(self.now,1030)
        self.assertEqual(sum(x[1] for x in self.trace),30)

    def test_return_http_never_retries_stop_budget_or_validation_refusals(self):
        self.http_retry_clock()
        for code in ("RELEASE_INTERRUPTED","CUTOVER_TIME_BUDGET_EXHAUSTED",
                     "SEALED_RESULT_SIZE_REFUSED","HTTP_STATUS_REFUSED","HTTP_TARGET_REFUSED"):
            error=m.Refused(code)
            with self.subTest(code=code),patch.object(self.backend,"previous_http",side_effect=error) as observe, \
                    self.assertRaises(m.Refused) as caught:
                self.backend.wait_previous_http()
            self.assertIs(caught.exception,error)
            self.assertEqual(observe.call_count,1)
        self.assertEqual(self.trace,[])

    def test_return_http_sleep_never_spends_remaining_global_budget(self):
        self.http_retry_clock()
        self.backend.started=0
        self.now=10799.875
        with patch.object(self.backend,"previous_http",side_effect=m.Refused("SEALED_OPERATION_REFUSED")) as observe, \
                self.assertRaisesRegex(m.Refused,"CUTOVER_TIME_BUDGET_EXHAUSTED"):
            self.backend.wait_previous_http()
        self.assertEqual(observe.call_count,1)
        self.assertEqual(self.trace,[("sleep",0.125)])
        self.assertEqual(self.now,10800)

    def initial_record(self):
        return {"schema_version":1,"release_sha256":self.backend.release.digest,
                "active_units":["nginx.service"],"foreign_masks":["vise.service"],
                "runtime_mask_intent":sorted(m.ALLOWED-{"vise.service"}),
                "http_status":{host:200 for host in m.DOMAINS}}

    @contextmanager
    def before_phase(self, initial=True):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root=Path(directory)
            state=root/"state"; volatile=root/"volatile"; generators=root/"generators"
            for path in (state,volatile,generators,state/"snapshot"):
                path.mkdir(mode=0o700)
            if initial:
                (state/"initial.json").write_text(json.dumps(self.initial_record()))
                (state/"initial.json").chmod(0o600)
            real_lstat=m.Path.lstat
            def owned(path):
                value=real_lstat(path)
                return SimpleNamespace(**{key:getattr(value,key) for key in dir(value) if key.startswith("st_")},
                                       **{}) if value.st_uid==0 else SimpleNamespace(**{
                    key:0 if key in ("st_uid","st_gid") else getattr(value,key)
                    for key in dir(value) if key.startswith("st_")})
            for attribute,value in (("STATE",state),("VOLATILE",volatile),("GENERATOR_DIRECTORY",generators)):
                stack.enter_context(patch.object(m,attribute,value))
            stack.enter_context(patch.object(m.Path,"lstat",owned))
            stack.enter_context(patch.object(m,"private_directory"))
            stack.enter_context(patch.object(m,"private_read",side_effect=lambda path,**_:json.loads(path.read_text())))
            yield state,volatile,generators

    def test_interrupted_initial_record_before_phase_can_be_reobserved(self):
        with self.before_phase() as (state,_,_):
            self.assertTrue(self.backend.prepare_preflight_retry())
            self.assertTrue((state/"initial.json").exists())
            self.assertEqual(self.trace[0],("verify_previous",))

    def test_preflight_retry_refuses_a_phase_snapshot_mask_gate_or_live_lease(self):
        for marker in ("phase","snapshot","mask","generator","gate","lease"):
            with self.subTest(marker=marker),self.before_phase() as (state,volatile,generators):
                if marker=="phase":(state/"phase.json").write_text("{}");
                if marker=="snapshot":(state/"snapshot"/"archive.tar").write_text("invented");
                if marker=="mask":(volatile/"masks.json").write_text("{}");
                if marker=="generator":(generators/m.GENERATOR_NAME).symlink_to("/missing");
                if marker=="lease":(volatile/"active.json").write_text('{"pid":12,"start_ticks":"34"}');
                with patch.object(self.backend.control,"execute",return_value=0 if marker=="gate" else 1), \
                        patch.object(self.backend,"live_lease",return_value=True),self.assertRaises(m.Refused):
                    self.backend.prepare_preflight_retry()

    def test_retry_removes_only_abandoned_metadata_even_link_publish_window(self):
        with self.before_phase() as (state,volatile,_):
            os.link(state/"initial.json",state/"initial.json.next")
            for path in (state/"phase.next",volatile/"active.json.next"):
                path.write_bytes(b'{"incomplete')
                path.chmod(0o600)
            self.assertTrue(self.backend.prepare_preflight_retry())
            self.assertEqual(set(p.name for p in state.iterdir()),{"snapshot","initial.json"})
            self.assertEqual((state/"initial.json").stat().st_nlink,1)
            self.assertEqual(list(volatile.iterdir()),[])

    def test_retry_never_uses_initial_record_for_another_release(self):
        with self.before_phase() as (state,_,_):
            value=self.initial_record(); value["release_sha256"]="f"*64
            (state/"initial.json").write_text(json.dumps(value))
            with self.assertRaisesRegex(m.Refused,"RECOVERY_RELEASE_MISMATCH"):
                self.backend.prepare_preflight_retry()

    def recover(self,value):
        self.backend.verify_artifacts=lambda:self.trace.append(("verify_artifacts",))
        self.backend.verify_guard_binding=lambda:self.trace.append(("verify_guard_binding",))
        self.backend.claim_lease=lambda:self.trace.append(("lease",))
        with patch.object(m,"private_read",return_value=value), \
                patch.object(m.os,"uname",return_value=SimpleNamespace(nodename=m.HOST)), \
                patch.object(m.os.path,"realpath",return_value=self.backend.generations.staged), \
                patch.object(m.Path,"is_symlink",return_value=False), \
                patch.object(m,"private_directory"),patch.object(m,"DeadlineSnapshot"):
            self.backend.preflight_recovery()

    def test_recovery_reloads_generator_only_after_ingress_gate_and_live_lease(self):
        self.phase=Phase.CANDIDATE
        self.recover(self.initial_record())
        gate=self.trace.index(("close_ingress",))
        lease=self.trace.index(("lease",))
        reload=self.trace.index(("execute",(self.backend.release.tools["systemctl"],"daemon-reload")))
        self.assertLess(gate,lease)
        self.assertLess(lease,reload)
        self.assertEqual(self.backend.control.masked_here,m.ALLOWED-{"vise.service"})
        self.assertLess(self.trace.index(("publish_masks",)),lease)
        self.assertEqual(self.backend.control.active_before,{"nginx.service"})

    def test_recovery_records_cannot_expand_units_or_claim_foreign_masks(self):
        for mutate in (lambda v:v.update(release_sha256="f"*64),
                       lambda v:v["active_units"].append("arbitrary.service"),
                       lambda v:v["active_units"].append("vise.service"),
                       lambda v:v["runtime_mask_intent"].remove("nginx.service"),
                       lambda v:v["active_units"].append({"bad":"type"})):
            value=self.initial_record()
            mutate(value)
            with self.assertRaises(m.Refused):
                self.recover(value)
        self.assertEqual(self.trace,[])

    def test_recovery_closed_after_returned_or_ambiguous_open(self):
        for phase in (Phase.OPENING,Phase.OPEN,Phase.HELD,Phase.RETURNED):
            self.phase=phase
            with self.assertRaisesRegex(m.Refused,"RECOVERY_PHASE_REFUSED"):
                self.recover(self.initial_record())
        self.assertEqual(self.trace,[])

    def test_lease_contains_process_start_ticks_and_invalid_documents_refuse(self):
        value=m.Backend.lease()
        self.assertEqual(set(value),{"pid","start_ticks"})
        self.assertTrue(value["start_ticks"].isdigit())
        for malformed in ({"pid":True,"start_ticks":"1"},{"pid":1,"start_ticks":"1"},
                          {"pid":99999,"start_ticks":1},{"pid":99999,"start_ticks":"1","extra":True}):
            with self.assertRaisesRegex(m.Refused,"LEASE_DOCUMENT_REFUSED"):
                m.Backend.live_lease(malformed)


class ManifestTests(unittest.TestCase):
    def test_release_is_hash_bound_and_mappings_are_read_only(self):
        release=sealed()
        with self.assertRaises(TypeError):
            release.tools["nft"]="invented"
        with self.assertRaisesRegex(m.Refused,"RELEASE_HASH_REFUSED"):
            m.Release(b"{}","0"*64)

    def test_free_commands_paths_unknown_fields_and_malformed_types_are_refused(self):
        mutations=(lambda v:v.update(argv=["anything"]),
                   lambda v:v["generations"].update(previous=invented("other-old")),
                   lambda v:v["generations"].update(staged=[]),
                   lambda v:v["generations"].update(staged=v["generations"]["promoted"]),
                   lambda v:v["tools"].update(nft="/run/current-system/sw/bin/nft"),
                   lambda v:v["tools"].update(nft=invented("nft")+"/bin/nft --flush"),
                   lambda v:v["helpers"].update(forgejo_governance="/tmp/invented"),
                   lambda v:v.update(ca_file="/var/lib/private"),
                   lambda v:v.update(generator="/run/current-system/bin/generator"),
                   lambda v:v.update(forgejo_binding_sha256=""),
                   lambda v:v.update(schema_version=True),
                   lambda v:v["artifacts"].pop(m.PREVIOUS),
                   lambda v:v["artifacts"].update({invented("unknown"):False}))
        for mutate in mutations:
            value=copy.deepcopy(manifest())
            mutate(value)
            with self.assertRaises(m.Refused):
                sealed(value)

    def test_ambiguous_json_is_refused(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'\xff',b''):
            with self.assertRaises(m.Refused):
                m.strict_json(raw)


if __name__ == "__main__":
    unittest.main()
