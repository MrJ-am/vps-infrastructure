# Registre des bases historiques et de leurs propriétaires.
# Les bibliothèques ASDF utilisent les rôles limités via le compte métier commun ;
# ce registre ne prescrit aucun compte Unix ou processus par bibliothèque.
# Fonction pure, également évaluée par les contrôles hors du VPS.
projects:
let
  ids = builtins.attrNames projects;
  validEntry = id:
    let entry = projects.${id}; in
    builtins.match "[a-z][a-z0-9-]*" id != null &&
    builtins.isAttrs entry && builtins.attrNames entry == [ "name" ] &&
    builtins.isString entry.name &&
    builtins.match "[a-z][a-z0-9_]{0,62}" entry.name != null &&
    builtins.match "pg_.*" entry.name == null &&
    !(builtins.elem entry.name [ "postgres" "template0" "template1" "root" "nobody" "all" "replication" ]);
  names = map (id: projects.${id}.name) ids;
  unique = values: builtins.length values == builtins.length (builtins.attrNames
    (builtins.listToAttrs (map (name: { inherit name; value = true; }) values)));
  join = builtins.concatStringsSep "\n";
in
assert builtins.isAttrs projects;
assert builtins.all validEntry ids;
assert unique names;
{
  databases = names;
  users = map (name: {
    inherit name;
    ensureDBOwnership = true;
    ensureClauses = {
      login = true;
      superuser = false;
      createdb = false;
      createrole = false;
      replication = false;
      bypassrls = false;
    };
  }) names;
  authentication = join (
    [ "local all postgres peer" ] ++
    map (name: ''local "${name}" "${name}" peer'') names ++
    [ "local all all reject" "host all all 0.0.0.0/0 reject" "host all all ::/0 reject" "" ]
  );
  permissionsSQL = join (map (name: ''
    BEGIN;
    REVOKE ALL PRIVILEGES ON DATABASE "${name}" FROM PUBLIC;
    GRANT CONNECT, TEMPORARY ON DATABASE "${name}" TO "${name}";
    COMMIT;
    \connect "${name}"
    BEGIN;
    REVOKE ALL PRIVILEGES ON SCHEMA public FROM PUBLIC;
    GRANT USAGE, CREATE ON SCHEMA public TO "${name}";
    COMMIT;
  '') names);
}
