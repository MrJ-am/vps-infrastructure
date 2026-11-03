// Fixed content-attestation extension. No workflow command is executed.
package run

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"os"
	"os/exec"
	"time"

	"golang.org/x/sys/unix"
)

const mrjamAttestationClient = "@attestation-client@"
const mrjamAttestationDirectory = "/var/lib/mrjam-forgejo-runner/attestations"
const mrjamAttestationLimit = 131072

type mrjamBoundedOutput struct {
	bytes.Buffer
	cancel context.CancelFunc
}

func (output *mrjamBoundedOutput) Write(raw []byte) (int, error) {
	if len(raw) > mrjamAttestationLimit-output.Len() {
		output.cancel()
		return 0, mrjamRefused("ATTESTATION_LIMIT")
	}
	return output.Buffer.Write(raw)
}

// The fixed client has already checked signature, exact policy and sender UID.
// This extra framing check binds the retained document to this admitted job.
func mrjamAttestationFrame(raw []byte, proposal string) error {
	if len(raw) == 0 || len(raw) > mrjamAttestationLimit || !mrjamDigest.MatchString(proposal) {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	var envelope struct {
		Schema    int             `json:"schema_version"`
		Algorithm string          `json:"algorithm"`
		KeyID     string          `json:"key_id"`
		Payload   json.RawMessage `json:"payload"`
		Signature string          `json:"signature"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&envelope) != nil || envelope.Schema != 1 || envelope.Algorithm != "Ed25519" || !mrjamDigest.MatchString(envelope.KeyID) {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	var suffix any
	if decoder.Decode(&suffix) != io.EOF {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	signature, err := base64.StdEncoding.Strict().DecodeString(envelope.Signature)
	if err != nil || len(signature) != 64 || base64.StdEncoding.EncodeToString(signature) != envelope.Signature {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	var payload struct {
		Proposal string `json:"proposal_sha256"`
		Scope    string `json:"scope"`
	}
	if json.Unmarshal(envelope.Payload, &payload) != nil || payload.Proposal != proposal || payload.Scope != "mrjam-validation-content-attestation-v1" {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	return nil
}

func mrjamKeepAttestation(directory, proposal string, raw []byte) error {
	if mrjamAttestationFrame(raw, proposal) != nil {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	if err := os.Mkdir(directory, 0700); err != nil && !os.IsExist(err) {
		return mrjamRefused("ATTESTATION_STORAGE_REFUSED")
	}
	parent, err := unix.Open(directory, unix.O_RDONLY|unix.O_DIRECTORY|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
	if err != nil {
		return mrjamRefused("ATTESTATION_STORAGE_REFUSED")
	}
	defer unix.Close(parent)
	var info unix.Stat_t
	if unix.Fstat(parent, &info) != nil || info.Uid != uint32(os.Getuid()) || info.Mode&07777 != 0700 {
		return mrjamRefused("ATTESTATION_STORAGE_REFUSED")
	}
	temporary := "." + proposal + ".next"
	fd, err := unix.Openat(parent, temporary, unix.O_WRONLY|unix.O_CREAT|unix.O_EXCL|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0400)
	if err != nil {
		return mrjamRefused("ATTESTATION_STORAGE_REFUSED")
	}
	defer unix.Unlinkat(parent, temporary, 0)
	file := os.NewFile(uintptr(fd), "fixed-attestation-output")
	defer file.Close()
	if size, err := file.Write(raw); err != nil || size != len(raw) {
		return mrjamRefused("ATTESTATION_STORAGE_REFUSED")
	}
	if file.Sync() != nil {
		return mrjamRefused("ATTESTATION_STORAGE_REFUSED")
	}
	if unix.Renameat(parent, temporary, parent, proposal+".json") != nil || unix.Fsync(parent) != nil {
		return mrjamRefused("ATTESTATION_STORAGE_REFUSED")
	}
	return nil
}

func mrjamRequestAttestation(ctx context.Context, proposal string) error {
	if !mrjamDigest.MatchString(proposal) {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	bounded, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	output := &mrjamBoundedOutput{cancel: cancel}
	command := exec.CommandContext(bounded, mrjamAttestationClient)
	command.Env = []string{"LANG=C", "LC_ALL=C", "MRJAM_PROPOSAL_DIGEST=" + proposal}
	command.Dir = "/"
	command.Stdin = nil
	command.Stdout = output
	command.Stderr = io.Discard
	command.WaitDelay = time.Second
	if command.Run() != nil || bounded.Err() != nil {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	return mrjamKeepAttestation(mrjamAttestationDirectory, proposal, output.Bytes())
}

func mrjamAfterCollection(ctx context.Context, proposal, rules string,
	collect func(context.Context, string, string) error,
	attest func(context.Context, string) error) error {
	if err := collect(ctx, proposal, rules); err != nil {
		return err
	}
	if ctx.Err() != nil {
		return mrjamRefused("ATTESTATION_REFUSED")
	}
	return attest(ctx, proposal)
}

func mrjamCollectAndAttest(ctx context.Context, proposal, rules string) error {
	return mrjamAfterCollection(ctx, proposal, rules, mrjamCollect, mrjamRequestAttestation)
}
