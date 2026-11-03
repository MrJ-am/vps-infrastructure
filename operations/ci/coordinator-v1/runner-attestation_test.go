package run

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// This fixture tests storage framing only. It is deliberately not a signature
// proof; the real Ed25519 and sender tests are in authority-v1/test_authority.py.
func mrjamEnvelopeFixture(t *testing.T, proposal string) []byte {
	t.Helper()
	raw, err := json.Marshal(map[string]any{"schema_version": 1, "algorithm": "Ed25519", "key_id": strings.Repeat("a", 64), "signature": base64.StdEncoding.EncodeToString(make([]byte, 64)), "payload": map[string]any{"proposal_sha256": proposal, "scope": "mrjam-validation-content-attestation-v1"}})
	if err != nil {
		t.Fatal("fixture refused")
	}
	return raw
}

func TestMRJAMAttestationFollowsCollectionOnly(t *testing.T) {
	for _, failed := range []bool{false, true} {
		calls := []string{}
		err := mrjamAfterCollection(context.Background(), strings.Repeat("b", 64), strings.Repeat("c", 40), func(_ context.Context, proposal, rules string) error {
			calls = append(calls, "collect")
			if proposal != strings.Repeat("b", 64) || rules != strings.Repeat("c", 40) {
				t.Fatal("binding changed")
			}
			if failed {
				return mrjamRefused("COLLECTION_REFUSED")
			}
			return nil
		}, func(_ context.Context, proposal string) error {
			calls = append(calls, "attest")
			return mrjamRefused("ATTESTATION_REFUSED")
		})
		if err == nil {
			t.Fatal("refusal lost")
		}
		want := "collect,attest"
		if failed {
			want = "collect"
		}
		if strings.Join(calls, ",") != want {
			t.Fatal("authority called before collection")
		}
	}
}

func TestMRJAMAttestationCancelledAfterCollection(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	called := false
	err := mrjamAfterCollection(ctx, strings.Repeat("b", 64), strings.Repeat("c", 40), func(context.Context, string, string) error { cancel(); return nil }, func(context.Context, string) error { called = true; return nil })
	if err == nil || called {
		t.Fatal("cancelled collection reached authority")
	}
}

func TestMRJAMAttestationOutputLimitCancelsChild(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	writer := &mrjamBoundedOutput{cancel: cancel}
	if _, err := writer.Write(make([]byte, mrjamAttestationLimit)); err != nil {
		t.Fatal("bounded payload refused")
	}
	if _, err := writer.Write([]byte("X")); err == nil || ctx.Err() == nil || writer.Len() != mrjamAttestationLimit {
		t.Fatal("excess output retained")
	}
}

func TestMRJAMAttestationStoredAtomicallyAndBoundToDigest(t *testing.T) {
	proposal := strings.Repeat("b", 64)
	directory := filepath.Join(t.TempDir(), "attestations")
	raw := mrjamEnvelopeFixture(t, proposal)
	if err := mrjamKeepAttestation(directory, proposal, raw); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(directory, proposal+".json")
	observed, err := os.ReadFile(file)
	if err != nil || !bytes.Equal(observed, raw) {
		t.Fatal("retained content differs")
	}
	info, err := os.Lstat(file)
	if err != nil || info.Mode().Perm() != 0400 {
		t.Fatal("unsafe retained metadata")
	}
	if err := mrjamKeepAttestation(directory, proposal, append(raw, '\n')); err != nil {
		t.Fatal("atomic repeat refused")
	}
	entries, err := os.ReadDir(directory)
	if err != nil || len(entries) != 1 {
		t.Fatal("temporary output retained")
	}
	before, _ := os.ReadFile(file)
	for _, bad := range [][]byte{mrjamEnvelopeFixture(t, strings.Repeat("c", 64)), append(raw, raw...), make([]byte, mrjamAttestationLimit+1)} {
		if mrjamKeepAttestation(directory, proposal, bad) == nil {
			t.Fatal("wrong document retained")
		}
		after, _ := os.ReadFile(file)
		if !bytes.Equal(before, after) {
			t.Fatal("refusal changed prior attestation")
		}
	}
}

func TestMRJAMAttestationStorageSymlinkAndPendingFileRefused(t *testing.T) {
	root := t.TempDir()
	proposal := strings.Repeat("b", 64)
	raw := mrjamEnvelopeFixture(t, proposal)
	target := filepath.Join(root, "target")
	if os.Mkdir(target, 0700) != nil {
		t.Fatal("fixture")
	}
	link := filepath.Join(root, "link")
	if os.Symlink(target, link) != nil {
		t.Fatal("fixture")
	}
	if mrjamKeepAttestation(link, proposal, raw) == nil {
		t.Fatal("symlink followed")
	}
	pending := filepath.Join(target, "."+proposal+".next")
	if os.WriteFile(pending, []byte("invented prior file"), 0400) != nil {
		t.Fatal("fixture")
	}
	if mrjamKeepAttestation(target, proposal, raw) == nil {
		t.Fatal("pending file overwritten")
	}
	observed, _ := os.ReadFile(pending)
	if string(observed) != "invented prior file" {
		t.Fatal("prior file changed")
	}
}
