"""Fetch exact PR objects into an isolated, disposable intake directory.

The caller supplies a private size-limited filesystem and a read-only token.
No checkout, candidate program, credential helper, submodule or LFS runs here.
Successful transport is not validation or permission to deploy.
"""
import base64
import os
from pathlib import Path
import resource
import signal
import stat
import subprocess

import github_proposals as P
import source_snapshot as S


def environment(token):
    S.require(type(token) is str and 0 < len(token) <= 4096
              and all(33 <= ord(c) <= 126 for c in token), 'TOKEN_FORMAT_REFUSED')
    authorization = base64.b64encode(('x-access-token:' + token).encode()).decode()
    settings = {
        'credential.helper': '', 'core.hooksPath': '/dev/null',
        'http.followRedirects': 'false', 'http.sslVerify': 'true',
        'http.proxy': '', 'http.extraHeader': '',
        'http.https://github.com/.extraHeader': 'Authorization: Basic ' + authorization,
        'protocol.allow': 'never', 'protocol.https.allow': 'always',
        'fetch.recurseSubmodules': 'false', 'maintenance.auto': 'false',
        'gc.auto': '0', 'init.templateDir': '',
        'core.askPass': '/nonexistent', 'fetch.fsckObjects': 'true',
    }
    env = {'LANG': 'C', 'LC_ALL': 'C', 'HOME': '/nonexistent',
           'PATH': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0',
           'GIT_NO_REPLACE_OBJECTS': '1', 'GIT_NO_LAZY_FETCH': '1',
           'GIT_ALLOW_PROTOCOL': 'https', 'GIT_LFS_SKIP_SMUDGE': '1',
           'GIT_CONFIG_COUNT': str(len(settings)),
           'GIT_SSL_CAINFO': '/etc/ssl/certs/ca-certificates.crt'}
    for index, (key, value) in enumerate(settings.items()):
        env['GIT_CONFIG_KEY_' + str(index)] = key
        env['GIT_CONFIG_VALUE_' + str(index)] = value
    return env


def limits():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024**2, 256 * 1024**2))


def execute(arguments, env):
    process = None
    try:
        process = subprocess.Popen(arguments, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True, preexec_fn=limits)
        result = process.wait(timeout=240)
    except (OSError, subprocess.TimeoutExpired):
        raise S.Refused('SOURCE_FETCH_UNAVAILABLE') from None
    finally:
        if process is not None:
            # Git may have spawned an HTTPS helper. Terminate the entire
            # isolated transport group before the caller revokes its token.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    S.require(result == 0, 'SOURCE_FETCH_REFUSED')


def fetch(directory, git, proposal, token, run=execute):
    # Revalidate the entire projected record, never interpolate branch text.
    S.require(type(proposal) is dict and set(proposal) == {
        'repository', 'repository_id', 'number', 'draft', 'head', 'base', 'branch'},
        'PROPOSAL_SHAPE_REFUSED')
    repository = proposal['repository']
    S.require(repository in P.REPOSITORIES
              and proposal['repository_id'] == P.REPOSITORIES[repository]
              and type(proposal['number']) is int and 0 < proposal['number'] < 2**31
              and proposal['draft'] is False, 'PROPOSAL_SCOPE_REFUSED')
    for key in ('base', 'head'):
        S.require(type(proposal[key]) is str and S.OID.fullmatch(proposal[key]),
                  'PROPOSAL_COMMIT_REFUSED')
    S.require(proposal['base'] != proposal['head'], 'PROPOSAL_UNCHANGED')
    root = Path(directory)
    info = root.lstat()
    S.require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
              and stat.S_IMODE(info.st_mode) == 0o700 and root.is_absolute()
              and root.resolve() == root and not any(root.iterdir()),
              'SOURCE_DIRECTORY_REFUSED')
    S.require(Path(git).is_absolute(), 'GIT_EXECUTABLE_REFUSED')
    env = environment(token)
    target = root / 'objects.git'
    run([str(git), 'init', '--bare', '--quiet', str(target)], env)
    run([str(git), '--git-dir=' + str(target), 'fetch', '--quiet', '--no-tags',
         '--no-write-fetch-head', '--no-recurse-submodules',
         'https://github.com/MrJ-am/' + repository + '.git',
         '+refs/heads/main:refs/intake/base',
         '+refs/pull/' + str(proposal['number']) + '/head:refs/intake/head'], env)
    reader = S.NativeObjects(target, git)
    for key in ('base', 'head'):
        actual = reader.command('rev-parse', '--verify', 'refs/intake/' + key).strip()
        S.require(actual == proposal[key].encode('ascii'), 'PROPOSAL_MOVED_DURING_FETCH')
    S.ancestry(reader, proposal['base'], proposal['head'])
    return reader


def receive(directory, git, proposal, credentials, request=P.api, run=execute):
    """Fresh API observation, exact objects, second observation, token revocation.

    Callers must still recheck the PR when admitting or merging it. This result
    does not promise the remote branch will remain unchanged after this call.
    """
    P.A.checked(credentials)
    S.require(credentials['app_id'] == P.APP_ID, 'APP_REFUSED')
    S.require(type(proposal) is dict and proposal.get('repository') in P.REPOSITORIES
              and type(proposal.get('number')) is int and 0 < proposal['number'] < 2**31,
              'PROPOSAL_SCOPE_REFUSED')
    repository = proposal['repository']
    path = '/repos/MrJ-am/' + repository + '/pulls/' + str(proposal['number'])
    status, created = request('/app/installations/' + str(P.INSTALLATION) + '/access_tokens',
                              P.A.jwt(credentials), 'POST', {
                                  'repository_ids': [P.REPOSITORIES[repository]],
                                  'permissions': P.READ_PERMISSIONS})
    S.require(status == 201 and type(created) is dict
              and type(created.get('token')) is str, 'READ_TOKEN_REFUSED')
    token = created['token']
    try:
        S.require(created.get('permissions') == P.READ_PERMISSIONS, 'TOKEN_PERMISSIONS_REFUSED')
        def observe():
            status, current = request(path, token)
            S.require(status == 200 and P.project(repository, current) == proposal,
                      'PROPOSAL_OBSERVATION_CHANGED')
        observe()
        reader = fetch(directory, git, proposal, token, run)
        observe()
        return reader
    finally:
        status, _ = request('/installation/token', token, 'DELETE')
        S.require(status == 204, 'TOKEN_REVOCATION_FAILED')
