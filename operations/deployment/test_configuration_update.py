"""Failure and crash ordering for the configuration-only state machine."""
import unittest
import configuration_update as C


class Adapter:
    def __init__(self, state=None, pair=("previous", "previous"), fail=None):
        self.state, self.pair, self.fail = state, pair, fail
        self.calls = []

    def call(self, name):
        self.calls.append(name)
        if self.fail == name:
            raise RuntimeError("synthetic refusal")

    def preflight(self): self.call("preflight")
    def read_checkpoint(self): return self.state
    def observe(self): return self.pair
    def checkpoint(self, state):
        self.call("checkpoint:" + state)
        self.state = state
    def activate_candidate(self):
        self.call("activate_candidate")
        self.pair = ("candidate", self.pair[1])
    def select_candidate_boot(self):
        self.call("select_candidate_boot")
        self.pair = (self.pair[0], "candidate")
    def activate_previous(self):
        self.call("activate_previous")
        self.pair = ("previous", self.pair[1])
    def select_previous_boot(self):
        self.call("select_previous_boot")
        self.pair = (self.pair[0], "previous")
    def verify_candidate(self): self.call("verify_candidate")
    def verify_previous(self): self.call("verify_previous")


class Tests(unittest.TestCase):
    def test_success_then_repeated_observation_without_mutation(self):
        a = Adapter()
        self.assertEqual(C.update(a), "CONFIGURATION_VERIFIED")
        self.assertLess(a.calls.index("verify_candidate"), a.calls.index("select_candidate_boot"))
        a.calls.clear()
        self.assertEqual(C.update(a), "CONFIGURATION_ALREADY_VERIFIED")
        self.assertEqual(a.calls, ["preflight", "verify_candidate"])

    def test_failures_return_without_any_data_operation(self):
        for point in ("activate_candidate", "verify_candidate", "select_candidate_boot",
                      "checkpoint:live-verified", "checkpoint:complete"):
            with self.subTest(point=point):
                a = Adapter(fail=point)
                self.assertEqual(C.update(a), "CONFIGURATION_RETURNED")
                self.assertEqual(a.pair, ("previous", "previous"))
                self.assertEqual(a.state, "returned")

    def test_crash_states_return_even_if_both_pointers_changed(self):
        for state in ("activating", "live-verified", "boot-selecting", "returning"):
            for pair in (("previous", "previous"), ("candidate", "previous"),
                         ("candidate", "candidate"), ("previous", "candidate")):
                with self.subTest(state=state, pair=pair):
                    a = Adapter(state, pair)
                    self.assertEqual(C.update(a), "CONFIGURATION_RETURNED")
                    self.assertNotIn("activate_candidate", a.calls)

    def test_foreign_and_inconsistent_states_refuse_without_switch(self):
        for state, pair in ((None, ("foreign", "previous")),
                            (None, ("candidate", "candidate")),
                            ("prepared", ("candidate", "previous")),
                            ("complete", ("previous", "previous")),
                            ("returned", ("candidate", "candidate")),
                            ("unknown", ("previous", "previous"))):
            with self.subTest(state=state, pair=pair):
                a = Adapter(state, pair)
                with self.assertRaises(C.Refused): C.update(a)
                self.assertEqual(a.calls, ["preflight"])

    def test_return_failure_never_marks_success(self):
        a = Adapter("returning", ("candidate", "candidate"), fail="activate_previous")
        with self.assertRaises(RuntimeError): C.update(a)
        self.assertEqual(a.state, "returning")
        self.assertNotIn("checkpoint:complete", a.calls)

    def test_preflight_refusal_precedes_every_effect(self):
        a = Adapter(fail="preflight")
        with self.assertRaises(RuntimeError): C.update(a)
        self.assertEqual(a.calls, ["preflight"])
        self.assertIsNone(a.state)

    def test_return_is_terminal_until_explicit_new_release(self):
        a = Adapter("returned")
        self.assertEqual(C.update(a), "CONFIGURATION_ALREADY_RETURNED")
        self.assertEqual(a.calls, ["preflight", "verify_previous"])


if __name__ == "__main__": unittest.main()
