package run

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	runnerv1 "code.forgejo.org/forgejo/actions-proto/runner/v1"
	"code.forgejo.org/forgejo/runner/v13/act/jobparser"
	"google.golang.org/protobuf/types/known/structpb"
)

func mrjamFixture(t *testing.T) (*runnerv1.Task, mrjamPolicy) {
	t.Helper()
	value, err := structpb.NewStruct(map[string]any{
		"repository": "MrJ-am/mrjam-validation", "repository_owner": "MrJ-am",
		"ref": "refs/heads/main", "ref_name": "main", "ref_type": "branch",
		"sha": strings.Repeat("a", 40), "event_name": "workflow_dispatch",
		"workflow_ref": "MrJ-am/mrjam-validation/.forgejo/workflows/independent-validation.yml@refs/heads/main",
		"event": map[string]any{"inputs": map[string]any{"proposal_digest": strings.Repeat("b", 64)}},
	})
	if err != nil { t.Fatal("fixture context") }
	workflows, err := jobparser.Parse(mrjamWorkflow, true)
	if err != nil || len(workflows) != 1 { t.Fatal("fixture parse") }
	payload, err := workflows[0].Marshal()
	if err != nil { t.Fatal("fixture serialization") }
	return &runnerv1.Task{Id: 123, Context: value, WorkflowPayload: payload}, mrjamPolicy{SchemaVersion: 1, RulesRevision: strings.Repeat("a", 40)}
}

func TestMRJAMAdmissionBeforeCollector(t *testing.T) {
	cases := []struct{name string; mutate func(*runnerv1.Task, *mrjamPolicy)}{
		{"other-repository", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["repository"] = structpb.NewStringValue("MrJ-am/candidate") }},
		{"unapproved-branch-same-label-and-content", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["ref"] = structpb.NewStringValue("refs/heads/candidate") }},
		{"tag", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["ref"] = structpb.NewStringValue("refs/tags/main") }},
		{"different-sha", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["sha"] = structpb.NewStringValue(strings.Repeat("c", 40)) }},
		{"different-event", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["event_name"] = structpb.NewStringValue("pull_request_target") }},
		{"different-workflow-ref", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["workflow_ref"] = structpb.NewStringValue("MrJ-am/mrjam-validation/.forgejo/workflows/other.yml@refs/heads/main") }},
		{"missing-provenance", func(task *runnerv1.Task, _ *mrjamPolicy) { delete(task.Context.Fields, "sha") }},
		{"no-context", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context = nil }},
		{"wrong-field-type", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["sha"] = structpb.NewBoolValue(true) }},
		{"missing-policy", func(_ *runnerv1.Task, policy *mrjamPolicy) { policy.RulesRevision = "" }},
		{"unknown-policy-version", func(_ *runnerv1.Task, policy *mrjamPolicy) { policy.SchemaVersion = 2 }},
		{"changed-shell-command", func(task *runnerv1.Task, _ *mrjamPolicy) { task.WorkflowPayload = []byte(strings.Replace(string(task.WorkflowPayload), "exec mrjam-submit-validation", "touch /tmp/unapproved-step-executed", 1)) }},
		{"additional-action", func(task *runnerv1.Task, _ *mrjamPolicy) { task.WorkflowPayload = append(task.WorkflowPayload, []byte("      - uses: unapproved/action@main\n")...) }},
		{"job-environment-injection", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Vars = map[string]string{"BASH_ENV": "/tmp/injected"} }},
		{"needs-context", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Needs = map[string]*runnerv1.TaskNeed{"untrusted": {}} }},
		{"shell-input", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["event"].GetStructValue().Fields["inputs"].GetStructValue().Fields["proposal_digest"] = structpb.NewStringValue("$(touch /tmp/injected)") }},
		{"extra-input", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["event"].GetStructValue().Fields["inputs"].GetStructValue().Fields["command"] = structpb.NewStringValue("echo injected") }},
		{"non-string-input", func(task *runnerv1.Task, _ *mrjamPolicy) { task.Context.Fields["event"].GetStructValue().Fields["inputs"].GetStructValue().Fields["proposal_digest"] = structpb.NewNumberValue(1) }},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			task, policy := mrjamFixture(t)
			test.mutate(task, &policy)
			opened := false
			err := mrjamExecute(context.Background(), task, policy, func(context.Context, string, string) error { opened = true; return nil })
			if err == nil || opened { t.Fatal("unapproved request reached collector") }
			if !strings.HasPrefix(err.Error(), "MRJAM_") || strings.Contains(err.Error(), "injected") { t.Fatal("unfiltered refusal") }
		})
	}
}

func TestMRJAMApprovedDigestOnly(t *testing.T) {
	task, policy := mrjamFixture(t)
	called := 0
	err := mrjamExecute(context.Background(), task, policy, func(_ context.Context, digest, rules string) error {
		called++
		if digest != strings.Repeat("b", 64) || rules != policy.RulesRevision { t.Fatal("changed identity") }
		return nil
	})
	if err != nil || called != 1 { t.Fatal("approved request not collected") }
}

func TestMRJAMWorkflowStructuralRefusals(t *testing.T) {
	for _, raw := range []string{
		"name: one\nname: two\njobs: {}\n",
		"name: &anchor hello\njobs: *anchor\n",
		"name: !custom hello\njobs: {}\n",
		"name: one\n---\nname: two\n",
		strings.Repeat("x", 32769),
	} {
		if _, err := mrjamCanonicalWorkflow([]byte(raw)); err == nil { t.Fatal("non-closed workflow accepted") }
	}
}

func TestMRJAMCollectorReceipt(t *testing.T) {
	value := map[string]any{"schema_version": 1, "decision": "passed", "proposal_sha256": strings.Repeat("b", 64),
		"rules_revision": strings.Repeat("a", 40), "authority": "local-controller-receipt", "collection": "retained-code-artifacts",
		"authenticated_validation_authority": false, "artifacts": []any{
			map[string]any{"name": "server", "bytes": 1, "sha256": strings.Repeat("c", 64)},
			map[string]any{"name": "frontend.tar", "bytes": 2, "sha256": strings.Repeat("d", 64)},
			map[string]any{"name": "verification.json", "bytes": 3, "sha256": strings.Repeat("e", 64)},
		}}
	encode := func() []byte { raw, err := json.Marshal(value); if err != nil { t.Fatal("fixture json") }; return raw }
	if err := mrjamValidateReceipt(encode(), strings.Repeat("b", 64), strings.Repeat("a", 40)); err != nil { t.Fatal("valid receipt refused") }
	for _, mutate := range []func(){
		func() { value["rules_revision"] = strings.Repeat("f", 40) },
		func() { value["rules_revision"] = strings.Repeat("a", 40); value["authenticated_validation_authority"] = true },
		func() { value["authenticated_validation_authority"] = false; value["decision"] = "failed" },
		func() { value["decision"] = "passed"; value["url"] = "http://untrusted.invalid" },
	} {
		mutate()
		if err := mrjamValidateReceipt(encode(), strings.Repeat("b", 64), strings.Repeat("a", 40)); err == nil { t.Fatal("invalid receipt accepted") }
	}
}

func TestMRJAMCanonicalJSONRejectsDuplicatesAndUnknownFields(t *testing.T) {
	for _, raw := range []string{
		`{"rules_revision":"a","rules_revision":"b","schema_version":1}`,
		`{"rules_revision":"a","schema_version":1,"unexpected":true}`,
		`{"rules_revision":"a","schema_version":1} {}`,
	} {
		var policy mrjamPolicy
		if mrjamJSON([]byte(raw), &policy, 2) == nil { t.Fatal("open JSON accepted") }
	}
}
