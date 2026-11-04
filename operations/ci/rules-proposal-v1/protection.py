"""Read-only main protection guard; no administrator API token is needed.

Forgejo17 SpecificReposAuthorizationReducer disables AllowAdminOverride.
Its protection API consequently refuses even a GET for the bounded token.
Read the fixed repository's metadata only, return one boolean, and retain
exactly the protection installed by the qualified governance reconciler.
"""
import lease

SQL = """BEGIN READ ONLY;
SET LOCAL statement_timeout='3s'; SET LOCAL search_path=pg_catalog;
SELECT (SELECT count(*)=1 FROM (REPO) r)
 AND (SELECT count(*)=1 FROM public.protected_branch WHERE repo_id IN (REPO))
 AND EXISTS(SELECT FROM public.protected_branch WHERE repo_id IN (REPO)
 AND branch_name='main' AND NOT can_push AND NOT enable_whitelist
 AND coalesce(nullif(whitelist_user_i_ds::jsonb,'null'::jsonb),'[]'::jsonb)='[]'::jsonb
 AND coalesce(nullif(whitelist_team_i_ds::jsonb,'null'::jsonb),'[]'::jsonb)='[]'::jsonb
 AND NOT whitelist_deploy_keys AND NOT enable_merge_whitelist
 AND coalesce(nullif(merge_whitelist_user_i_ds::jsonb,'null'::jsonb),'[]'::jsonb)='[]'::jsonb
 AND coalesce(nullif(merge_whitelist_team_i_ds::jsonb,'null'::jsonb),'[]'::jsonb)='[]'::jsonb
 AND enable_status_check AND status_check_contexts::jsonb='["mrjam/independent-validation"]'::jsonb
 AND required_approvals=1 AND NOT enable_approvals_whitelist
 AND coalesce(nullif(approvals_whitelist_user_i_ds::jsonb,'null'::jsonb),'[]'::jsonb)='[]'::jsonb
 AND coalesce(nullif(approvals_whitelist_team_i_ds::jsonb,'null'::jsonb),'[]'::jsonb)='[]'::jsonb
 AND block_on_rejected_reviews AND block_on_official_review_requests AND block_on_outdated_branch
 AND dismiss_stale_approvals AND NOT ignore_stale_approvals AND NOT require_signed_commits
 AND protected_file_patterns='' AND unprotected_file_patterns='' AND apply_to_admins);
COMMIT;""".replace("REPO", lease.SELECT_REPO)


def verify(bootstrap):
    raw = bootstrap.command([bootstrap.PSQL,"-X","-w","-qAt","-h","/run/postgresql",
        "-d","forgejo","-v","ON_ERROR_STOP=1"],SQL.encode())
    lease.require(raw == b"t\n", "MAIN_PROTECTION_REFUSED")
    return True
