---
name: start-mrjam-synthetic-environment
description: Start and check the already-installed, private Codex development environment for MRJ.AM using only synthetic local services.
---

This is the versioned source for the Cloud environment's **Start skill** field.
Its location here does not automatically configure that field.

1. Locate the selected `vps-infrastructure` checkout and its `environment/`
   directory. Read `environment/README.org` and the repository's `AGENTS.md`.
2. Run `bash environment/setup.sh --check` from the checkout root. If it fails,
   report the fixed error code or incomplete checks. Do not silently update the
   pins or install a different runtime. Environment preparation can run the
   reviewed `bash environment/setup.sh --install`, then repeat the check.
3. Source `environment/.local/activate.sh` in every shell that needs the tools.
   An export from the installation conversation is not proof that later tasks
   inherit the same PATH.
4. Run `bash environment/services.sh up`, then
   `bash environment/check.sh --services`. Both must succeed. Services are
   PostgreSQL 17.11 with pgvector 0.8.7 at `127.0.0.1:55432` and a synthetic Nginx endpoint at
   `http://127.0.0.1:18080/__synthetic__/ready`.
5. Use only the synthetic database URL named `MRJAM_SYNTHETIC_DATABASE_URL`.
   The helper initializes vector only in the literal disposable database;
   it does not run a historical application migration. Give concurrent domain
   tests separate schemas. Never load an application
   database, backup, user corpus, production cookie or real traffic.
6. Report verified tool versions and readiness, then follow the requested task.
   Do not stop the shared synthetic services while other tasks in this workspace
   are using them. `services.sh down` explicitly discards their synthetic data.

These instructions grant no production permissions and do not install a
privileged runner. They do not connect Forgejo, SSH, DNS, secrets or a VPN, and
do not enable deployment workflows. The Docker bridge is for local development;
it is not the production CI isolation design. Missing platform support is a
precondition to resolve, never permission to create paid infrastructure.

