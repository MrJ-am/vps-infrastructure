// Synthetic delivery of an admitted task. Every called production function is
// copied unchanged by the normal runner derivation; no Forgejo API is modeled.
package run

import (
  "context"
  "testing"
  "google.golang.org/protobuf/types/known/structpb"
)

func TestMRJAMSystemdBoundedChain(t *testing.T) {
  task,policy:=mrjamFixture(t)
  policy.RulesRevision="@rules@"
  task.Context.Fields["sha"]=structpb.NewStringValue(policy.RulesRevision)
  task.Context.Fields["event"].GetStructValue().Fields["inputs"].GetStructValue().Fields["proposal_digest"]=structpb.NewStringValue("@proposal@")
  if err:=mrjamExecute(context.Background(),task,policy,mrjamCollectAndAttest);err!=nil{t.Fatal(err)}
}
