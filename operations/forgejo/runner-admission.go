// MRJ.am fixed collector adapter for the pinned Forgejo runner.
// No candidate shell, action, checkout, hook or subprocess is executed here.
package run

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	runnerv1 "code.forgejo.org/forgejo/actions-proto/runner/v1"
	"code.forgejo.org/forgejo/runner/v13/act/jobparser"
	"code.forgejo.org/forgejo/runner/v13/internal/pkg/report"
	"github.com/sirupsen/logrus"
	"go.yaml.in/yaml/v3"
	"golang.org/x/sys/unix"
)

const mrjamAdmissionPath = "/etc/mrjam-forgejo-runner/admission.json"
const mrjamCollectorSocket = "/run/mrjam-validation-collector/request.sock"

//go:embed mrjam_workflow.yml
var mrjamWorkflow []byte

var mrjamCommit = regexp.MustCompile(`^[0-9a-f]{40}$`)
var mrjamDigest = regexp.MustCompile(`^[0-9a-f]{64}$`)

type mrjamPolicy struct {
	RulesRevision string `json:"rules_revision"`
	SchemaVersion int    `json:"schema_version"`
}

func mrjamRefused(code string) error { return errors.New("MRJAM_" + code) }

// Require canonical closed JSON. Re-encoding a generic value also rejects
// duplicate keys, including nested ones, before decoding the typed contract.
func mrjamJSON(raw []byte, target any, fields int) error {
	var canonical map[string]any
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&canonical); err != nil || len(canonical) != fields {
		return mrjamRefused("INVALID_JSON")
	}
	encoded, err := json.Marshal(canonical)
	if err != nil || !bytes.Equal(bytes.TrimSpace(raw), encoded) {
		return mrjamRefused("NONCANONICAL_JSON")
	}
	decoder = json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return mrjamRefused("INVALID_JSON")
	}
	return nil
}

func mrjamReadPolicy() (mrjamPolicy, error) {
	var policy mrjamPolicy
	fd, err := unix.Open(mrjamAdmissionPath, unix.O_RDONLY|unix.O_NOFOLLOW|unix.O_NONBLOCK|unix.O_CLOEXEC, 0)
	if err != nil {
		return policy, mrjamRefused("POLICY_UNAVAILABLE")
	}
	file := os.NewFile(uintptr(fd), mrjamAdmissionPath)
	defer file.Close()
	var meta unix.Stat_t
	if unix.Fstat(fd, &meta) != nil || meta.Mode&unix.S_IFMT != unix.S_IFREG || meta.Uid != 0 || meta.Mode&0222 != 0 || meta.Nlink != 1 || meta.Size <= 0 || meta.Size > 4096 {
		return policy, mrjamRefused("UNSAFE_POLICY")
	}
	for path := filepath.Dir(mrjamAdmissionPath); ; path = filepath.Dir(path) {
		var parent unix.Stat_t
		if unix.Lstat(path, &parent) != nil || parent.Mode&unix.S_IFMT != unix.S_IFDIR || parent.Uid != 0 || parent.Mode&0022 != 0 {
			return policy, mrjamRefused("UNSAFE_POLICY")
		}
		if path == "/" { break }
	}
	raw, err := io.ReadAll(io.LimitReader(file, 4097))
	if err != nil || len(raw) > 4096 || int64(len(raw)) != meta.Size {
		return policy, mrjamRefused("INVALID_POLICY")
	}
	if err = mrjamJSON(raw, &policy, 2); err != nil || policy.SchemaVersion != 1 || !mrjamCommit.MatchString(policy.RulesRevision) {
		return policy, mrjamRefused("INVALID_POLICY")
	}
	return policy, nil
}

// Forgejo reserializes a selected job. Equality ignores presentation only;
// aliases, anchors, duplicate fields and all unexpected structure are refused.
func mrjamYAMLNode(node *yaml.Node, depth int) (any, error) {
	if node == nil || depth > 20 || node.Anchor != "" || node.Alias != nil { return nil, mrjamRefused("WORKFLOW_REFUSED") }
	switch node.Kind {
	case yaml.DocumentNode:
		if len(node.Content) != 1 { return nil, mrjamRefused("WORKFLOW_REFUSED") }
		return mrjamYAMLNode(node.Content[0], depth+1)
	case yaml.MappingNode:
		if len(node.Content)%2 != 0 || len(node.Content) > 100 { return nil, mrjamRefused("WORKFLOW_REFUSED") }
		result := map[string]any{}
		for index := 0; index < len(node.Content); index += 2 {
			key := node.Content[index]
			if key.Kind != yaml.ScalarNode || key.Tag != "!!str" || key.Anchor != "" || key.Alias != nil { return nil, mrjamRefused("WORKFLOW_REFUSED") }
			if _, exists := result[key.Value]; exists { return nil, mrjamRefused("WORKFLOW_REFUSED") }
			value, err := mrjamYAMLNode(node.Content[index+1], depth+1)
			if err != nil { return nil, err }
			result[key.Value] = value
		}
		return result, nil
	case yaml.SequenceNode:
		if len(node.Content) > 32 { return nil, mrjamRefused("WORKFLOW_REFUSED") }
		result := []any{}
		for _, child := range node.Content {
			value, err := mrjamYAMLNode(child, depth+1)
			if err != nil { return nil, err }
			result = append(result, value)
		}
		return result, nil
	case yaml.ScalarNode:
		if node.Tag != "!!str" && node.Tag != "!!int" && node.Tag != "!!bool" && node.Tag != "!!null" { return nil, mrjamRefused("WORKFLOW_REFUSED") }
		return [2]string{node.Tag, node.Value}, nil
	default:
		return nil, mrjamRefused("WORKFLOW_REFUSED")
	}
}

func mrjamCanonicalWorkflow(raw []byte) ([]byte, error) {
	if len(raw) == 0 || len(raw) > 32768 { return nil, mrjamRefused("WORKFLOW_REFUSED") }
	var document yaml.Node
	decoder := yaml.NewDecoder(bytes.NewReader(raw))
	if decoder.Decode(&document) != nil { return nil, mrjamRefused("WORKFLOW_REFUSED") }
	var extra yaml.Node
	if decoder.Decode(&extra) != io.EOF { return nil, mrjamRefused("WORKFLOW_REFUSED") }
	value, err := mrjamYAMLNode(&document, 0)
	if err != nil { return nil, err }
	return json.Marshal(value)
}

func mrjamExpectedWorkflow() ([]byte, error) {
	// Forgejo sends a serialized SingleWorkflow, not the repository's YAML
	// bytes. For example timeout-minutes becomes a quoted string. Normalize
	// only our compiled-in template with the pinned upstream parser. The
	// received task still goes through the strict closed YAML comparison.
	workflows, err := jobparser.Parse(mrjamWorkflow, true)
	if err != nil || len(workflows) != 1 { return nil, mrjamRefused("PINNED_WORKFLOW_INVALID") }
	raw, err := workflows[0].Marshal()
	if err != nil { return nil, mrjamRefused("PINNED_WORKFLOW_INVALID") }
	return mrjamCanonicalWorkflow(raw)
}

func mrjamAdmit(task *runnerv1.Task, policy mrjamPolicy) (string, error) {
	if task == nil || task.Context == nil || !mrjamCommit.MatchString(policy.RulesRevision) || policy.SchemaVersion != 1 {
		return "", mrjamRefused("PROVENANCE_REFUSED")
	}
	for field, expected := range map[string]string{
		"repository": "MrJ-am/mrjam-validation", "repository_owner": "MrJ-am",
		"ref": "refs/heads/main", "ref_name": "main", "ref_type": "branch",
		"sha": policy.RulesRevision, "event_name": "workflow_dispatch",
		"workflow_ref": "MrJ-am/mrjam-validation/.forgejo/workflows/independent-validation.yml@refs/heads/main",
	} {
		if task.Context.Fields[field].GetStringValue() != expected { return "", mrjamRefused("PROVENANCE_REFUSED_" + strings.ToUpper(field)) }
	}
	if len(task.Needs) != 0 || len(task.Vars) != 0 { return "", mrjamRefused("DYNAMIC_CONTEXT_REFUSED") }
	actual, err := mrjamCanonicalWorkflow(task.WorkflowPayload)
	if err != nil { return "", err }
	expected, err := mrjamExpectedWorkflow()
	if err != nil || !bytes.Equal(actual, expected) { return "", mrjamRefused("WORKFLOW_REFUSED") }
	event := task.Context.Fields["event"].GetStructValue()
	if event == nil { return "", mrjamRefused("INPUT_REFUSED") }
	inputs := event.Fields["inputs"].GetStructValue()
	if inputs == nil || len(inputs.Fields) != 1 { return "", mrjamRefused("INPUT_REFUSED") }
	proposal := inputs.Fields["proposal_digest"].GetStringValue()
	if !mrjamDigest.MatchString(proposal) { return "", mrjamRefused("INPUT_REFUSED") }
	return proposal, nil
}

type mrjamArtifact struct {
	Name string `json:"name"`
	Bytes int64 `json:"bytes"`
	SHA256 string `json:"sha256"`
}
type mrjamReceipt struct {
	SchemaVersion int `json:"schema_version"`
	Decision string `json:"decision"`
	Proposal string `json:"proposal_sha256"`
	Rules string `json:"rules_revision"`
	Artifacts []mrjamArtifact `json:"artifacts"`
	Authority string `json:"authority"`
	Collection string `json:"collection"`
	Authenticated bool `json:"authenticated_validation_authority"`
}

func mrjamValidateReceipt(raw []byte, proposal, rules string) error {
	var receipt mrjamReceipt
	if err := mrjamJSON(raw, &receipt, 8); err != nil { return err }
	if receipt.SchemaVersion != 1 || receipt.Decision != "passed" || receipt.Proposal != proposal || receipt.Rules != rules || receipt.Authority != "local-controller-receipt" || receipt.Collection != "retained-code-artifacts" || receipt.Authenticated || len(receipt.Artifacts) != 3 {
		return mrjamRefused("COLLECTOR_REFUSED")
	}
	for index, name := range []string{"server", "frontend.tar", "verification.json"} {
		item := receipt.Artifacts[index]
		limit := int64(64*1024*1024)
		if index == 2 { limit = 65536 }
		if item.Name != name || item.Bytes <= 0 || item.Bytes > limit || !mrjamDigest.MatchString(item.SHA256) { return mrjamRefused("COLLECTOR_REFUSED") }
	}
	return nil
}

func mrjamCollect(ctx context.Context, proposal, rules string) error {
	var meta unix.Stat_t
	if unix.Lstat(mrjamCollectorSocket, &meta) != nil || meta.Mode&unix.S_IFMT != unix.S_IFSOCK || meta.Uid != 0 || meta.Mode&0777 != 0660 { return mrjamRefused("COLLECTOR_UNTRUSTED") }
	connection, err := (&net.Dialer{Timeout: 5*time.Second}).DialContext(ctx, "unix", mrjamCollectorSocket)
	if err != nil { return mrjamRefused("COLLECTOR_UNAVAILABLE") }
	defer connection.Close()
	stop := context.AfterFunc(ctx, func() { _ = connection.Close() })
	defer stop()
	unixConnection, ok := connection.(*net.UnixConn)
	if !ok { return mrjamRefused("COLLECTOR_UNTRUSTED") }
	raw, err := unixConnection.SyscallConn()
	if err != nil { return mrjamRefused("COLLECTOR_UNTRUSTED") }
	trusted := false
	err = raw.Control(func(fd uintptr) { credentials, failure := unix.GetsockoptUcred(int(fd), unix.SOL_SOCKET, unix.SO_PEERCRED); trusted = failure == nil && credentials.Uid == 0 })
	if err != nil || !trusted { return mrjamRefused("COLLECTOR_UNTRUSTED") }
	deadline := time.Now().Add(1850*time.Second)
	if parent, exists := ctx.Deadline(); exists && parent.Before(deadline) { deadline = parent }
	if connection.SetDeadline(deadline) != nil { return mrjamRefused("COLLECTOR_UNAVAILABLE") }
	if size, failure := io.WriteString(connection, proposal+"\n"); failure != nil || size != 65 { return mrjamRefused("COLLECTOR_UNAVAILABLE") }
	if unixConnection.CloseWrite() != nil { return mrjamRefused("COLLECTOR_UNAVAILABLE") }
	receipt, err := io.ReadAll(io.LimitReader(connection, 4097))
	if err != nil || len(receipt) > 4096 { return mrjamRefused("COLLECTOR_REFUSED") }
	return mrjamValidateReceipt(receipt, proposal, rules)
}

func mrjamRun(ctx context.Context, task *runnerv1.Task, reporter *report.Reporter) error {
	policy, err := mrjamReadPolicy()
	if err != nil { logrus.Error(err); return err }
	// These functions return only our fixed refusal codes, never task content,
	// credentials, protocol responses or underlying system error text.
	if err = mrjamExecute(ctx, task, policy, mrjamCollect); err != nil { logrus.Error(err); return err }
	// Explicit reporting avoids dependence on upstream logger thresholds. This
	// status is a notification, never a deployment authorization or signature.
	return reporter.Fire(&logrus.Entry{Time: time.Now(), Level: logrus.InfoLevel,
		Message: "MRJAM_CODE_ARTIFACTS_COLLECTED_NO_DEPLOYMENT_AUTHORITY",
		Data: logrus.Fields{"jobResult": "success", "jobOutputs": map[string]string{}}})
}

func mrjamExecute(ctx context.Context, task *runnerv1.Task, policy mrjamPolicy, collect func(context.Context, string, string) error) error {
	proposal, err := mrjamAdmit(task, policy)
	if err != nil { return err }
	// No source checkout, workflow interpolation, action or shell is reachable.
	// The only request is the already-validated digest sent as data.
	return collect(ctx, proposal, policy.RulesRevision)
}
