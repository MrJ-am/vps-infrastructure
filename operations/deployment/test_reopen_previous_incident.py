"""Four persisted incident-helper tests; all service operations are injected.

Run this file directly with Python on the review host. The helper's fixed
controller package must already exist; no production preflight is executed.
"""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

source = Path(__file__).with_name("reopen-previous-20261102.py")
spec = importlib.util.spec_from_file_location("previous_incident_fixture", source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(failure=None):
    trace = []

    def call(name):
        def action(*args, **kwargs):
            trace.append((name, *args))
            if name == "start" and args[0][0] in m.TIMER_BINDINGS and failure:
                raise failure
        return action

    control = NS(active_before=set(m.CORE) | set(m.TIMER_BINDINGS) |
        {"vise.service", "forgejo-identity.service", "acme-setup.service"}, foreign_masks=set())
    for name in ("close_ingress", "publish_masks", "execute", "verify_masks",
                 "release_masks", "start", "open_ingress"):
        setattr(control, name, call(name))
    backend = NS(control=control, claim_lease=call("lease"), checkpoint=NS(write=call("phase")),
        release=NS(tools={"systemctl": "/fixed/systemctl"}), wait_previous_http=call("http"),
        generations=NS(previous="previous", select_boot=call("boot")),
        incident_held_phase={"schema_version": 1, "phase": m.Phase.HELD.value, "elapsed_seconds": 123})
    return backend, trace


class IncidentTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(m, "preflight"))
        self.enterContext(patch.object(m, "present", return_value=False))

    def test_success_orders_checkpoint_network_and_explicit_timer_targets(self):
        backend, trace = fixture()
        with patch.object(m, "publish_private", side_effect=lambda path, value: trace.append(("publish", path))):
            result = m.resume(backend)
        self.assertEqual(result["code"], "PREVIOUS_PUBLIC_REOPENED")
        phase = trace.index(("phase", m.Phase.RETURNED, 0))
        self.assertLess(trace.index(("publish", m.HELD_PHASE)), phase)
        self.assertLess(phase, next(i for i, item in enumerate(trace) if item[0] == "release_masks"))
        opened = trace.index(("open_ingress",))
        self.assertLess(trace.index(("http",)), opened)
        self.assertLess(trace.index(("boot", "previous")), opened)
        started = []
        for index, item in enumerate(trace):
            if item[0] != "start":
                continue
            started.extend(item[1])
            for timer in item[1]:
                if timer in m.TIMER_BINDINGS:
                    self.assertGreater(index, opened)
                    self.assertTrue(any(prior[0] == "release_masks" and m.TIMER_BINDINGS[timer] in prior[1]
                                        for prior in trace[opened:index]))
        self.assertEqual(set(started), set(m.CORE) | set(m.TIMER_BINDINGS))

    def test_failed_private_http_never_opens(self):
        backend, trace = fixture()
        backend.wait_previous_http = lambda: (_ for _ in ()).throw(m.Refused("HTTP_REFUSED"))
        with patch.object(m, "publish_private"), self.assertRaises(m.Refused):
            m.resume(backend)
        self.assertNotIn(("open_ingress",), trace)

    def test_timer_system_refusal_keeps_public_service_open(self):
        backend, trace = fixture(m.SystemRefused("invented timer refusal"))
        with patch.object(m, "publish_private"):
            result = m.resume(backend)
        self.assertEqual(result["code"], "PREVIOUS_PUBLIC_REOPENED_TIMERS_PENDING")
        self.assertEqual(len(result["timers_pending"]), len(m.TIMER_BINDINGS))
        self.assertEqual(sum(item[0] == "close_ingress" for item in trace), 1)

    def test_backend_deadline_is_not_absorbed_as_a_timer_refusal(self):
        backend, trace = fixture(m.Refused("CUTOVER_TIME_BUDGET_EXHAUSTED"))
        with patch.object(m, "publish_private"), self.assertRaisesRegex(m.Refused, "CUTOVER_TIME_BUDGET_EXHAUSTED"):
            m.resume(backend)
        self.assertEqual(sum(item[0] == "start" and item[1][0] in m.TIMER_BINDINGS for item in trace), 1)
        self.assertEqual(sum(item[0] == "close_ingress" for item in trace), 1)


if __name__ == "__main__":
    unittest.main()
