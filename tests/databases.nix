let
  generate = import ../lib/databases.nix;
  registry = builtins.fromJSON (builtins.readFile ../databases.json);
  current = generate registry;
  extended = generate (registry // { example.name = "example"; });
  invalid = projects: !(builtins.tryEval (builtins.deepSeq (generate projects) true)).success;
in
assert builtins.elem "matheval" current.databases;
assert builtins.elem "vision" current.databases;
assert builtins.elem "example" extended.databases;
assert (builtins.head current.users).ensureDBOwnership;
assert !(builtins.head current.users).ensureClauses.superuser;
assert builtins.match ".*local all all reject.*" extended.authentication != null;
assert invalid { x.name = "postgres"; };
assert invalid { x.name = "pg_read_all_data"; };
assert invalid { x.name = "a\nlocal all all trust"; };
assert invalid { x.name = "shared"; y.name = "shared"; };
assert invalid { x = { name = "x"; superuser = true; }; };
{ databasesDistinct = true; invalidReservationsRejected = true; }
