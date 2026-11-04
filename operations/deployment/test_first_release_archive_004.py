"""Real filesystem moves/locks, invented data; live services are replaced.

OWNER and the fixed directories use private local fixtures. Staged file bytes
must never be opened by the helper, including during the supposedly RO probe.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import first_release_archive_004 as m


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        local = Path(__file__).resolve().parents[2] / '.local'
        self.temp = tempfile.TemporaryDirectory(prefix='archive-return-004-test-', dir=local)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.uid, self.gid = os.geteuid(), os.getegid()
        self.old_umask = os.umask(0o077)
        self.addCleanup(os.umask, self.old_umask)
        paths = {'STATE': self.base/'cutover/first-deployment', 'ARCHIVE': self.base/'cutover/attempt-004',
                 'PRIOR_ARCHIVE': self.base/'cutover/attempt-002',
                 'EARLIER_ARCHIVE': self.base/'cutover/attempt-001',
                 'THIRD_ARCHIVE': self.base/'cutover/attempt-003',
                 'THIRD_RUNTIME_ARCHIVE': self.base/'run/retained-003',
                 'EARLIER_RUNTIME_ARCHIVE': self.base/'run/retained-001',
                 'PRIOR_RUNTIME_ARCHIVE': self.base/'run/retained-002',
                 'VOLATILE': self.base/'run/mrjam-cutover', 'RUNTIME_ARCHIVE': self.base/'run/retained',
                 'GUARD': self.base/'run/systemd/system-generators/mrjam-first-cutover-guard',
                 'RESULT': self.base/'run/status/result.json'}
        for key, path in paths.items():
            p = patch.object(m, key, path);p.start();self.addCleanup(p.stop)
        p = patch.object(m, 'OWNER', (self.uid,self.gid));p.start();self.addCleanup(p.stop)
        profiles = {name:(self.uid,self.gid,values[2]) for name,values in m.RUNTIME.items()}
        p = patch.object(m, 'RUNTIME', profiles);p.start();self.addCleanup(p.stop)
        for directory in (m.STATE,m.VOLATILE,m.GUARD.parent,m.RESULT.parent,m.PRIOR_ARCHIVE,m.PRIOR_RUNTIME_ARCHIVE,m.EARLIER_ARCHIVE,m.EARLIER_RUNTIME_ARCHIVE,m.THIRD_ARCHIVE,m.THIRD_RUNTIME_ARCHIVE):
            directory.mkdir(mode=0o700, parents=True)
        m.GUARD.parent.chmod(0o755)
        self.json(m.PRIOR_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'FIRST_RELEASE_ATTEMPT_ARCHIVED'})
        self.json(m.EARLIER_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'FIRST_RELEASE_ATTEMPT_ARCHIVED'})
        self.json(m.THIRD_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'FIRST_RELEASE_ATTEMPT_ARCHIVED'})
        (m.THIRD_ARCHIVE/'kept-private-snapshot').write_bytes(b'THIRD SNAPSHOT UNCHANGED')
        (m.THIRD_RUNTIME_ARCHIVE/'kept-private-staging').write_bytes(b'THIRD STAGING UNCHANGED')
        (m.PRIOR_ARCHIVE/'kept-private-snapshot').write_bytes(b'PRIOR SNAPSHOT UNCHANGED')
        (m.PRIOR_RUNTIME_ARCHIVE/'kept-private-staging').write_bytes(b'PRIOR STAGING UNCHANGED')
        (m.EARLIER_ARCHIVE/'kept-private-snapshot').write_bytes(b'EARLIER SNAPSHOT UNCHANGED')
        (m.EARLIER_RUNTIME_ARCHIVE/'kept-private-staging').write_bytes(b'EARLIER STAGING UNCHANGED')
        self.release = m.Release.immutable_file(m.RELEASE_PATH,m.RELEASE_SHA256)
        self.backend = m.Backend(self.release)
        self.units = ['mrjam-archive-mail-adopt.service','vise.service']
        self.foreign = 'mrjam-rust-green.service'
        self.commands = []
        self.reloaded = False
        def execute(args, **kwargs):
            self.commands.append(tuple(args))
            if args[-1] == 'daemon-reload':self.reloaded = True
            if m.CONTROLLER_UNIT in args:return 'LoadState=loaded\nActiveState=failed\nSubState=failed\nMainPID=0\nExecMainCode=1\nExecMainStatus=1\n'
            return 1 if 'nft' in args[0] else 0
        def properties(unit):
            return {'LoadState':'masked' if not self.reloaded or unit==self.foreign else 'loaded',
                    'ActiveState':'inactive','MainPID':'0','UnitFileState':'static'}
        self.backend.control = SimpleNamespace(execute=execute,properties=properties)
        self.backend.previous_http = lambda: self.backend.original['http_status']
        initial = {'schema_version':1,'release_sha256':m.RELEASE_SHA256,
                   'active_units':['nginx.service','postgresql.service'],'foreign_masks':[self.foreign],
                   'runtime_mask_intent':sorted(m.ALLOWED-{self.foreign}),
                   'http_status':{name:200 for name in __import__('release_backend').DOMAINS}}
        documents = {
            'initial.json':initial,
            'adoption-started.json':{'schema_version':1,'release_sha256':m.RELEASE_SHA256},
            'phase.json':{'schema_version':1,'phase':m.Phase.RETURNED.value,'elapsed_seconds':0},
            'failure.json':{'schema_version':1,'release_sha256':m.RELEASE_SHA256,'step':'readiness','component':'vision-frontend','code':'SEALED_OPERATION_REFUSED'},
        }
        for name,value in documents.items():self.json(m.STATE/name,value)
        self.json(m.VOLATILE/'masks.json',{'schema_version':1,'units':self.units})
        self.json(m.RESULT,{'schema_version':1,'code':'CUTOVER_REFUSED_PREVIOUS_GENERATION_RESTORED','phase':m.Phase.RETURNED.value})
        (m.STATE/'transaction.lock').write_bytes(b'')
        m.GUARD.symlink_to(self.release.generator)
        snapshot = m.STATE/'snapshot';snapshot.mkdir(mode=0o700)
        (snapshot/'candidate-state-retained').mkdir(mode=0o700)
        self.forbidden = []
        self.prior_forbidden = [m.PRIOR_ARCHIVE/"kept-private-snapshot", m.PRIOR_RUNTIME_ARCHIVE/"kept-private-staging", m.EARLIER_ARCHIVE/"kept-private-snapshot", m.EARLIER_RUNTIME_ARCHIVE/"kept-private-staging", m.THIRD_ARCHIVE/"kept-private-snapshot", m.THIRD_RUNTIME_ARCHIVE/"kept-private-staging"]
        for path in (snapshot/'paired-state.tar',snapshot/'paired-state.json',snapshot/'candidate-state-retained/private'):
            path.write_bytes(b'INVENTED PRIVATE SNAPSHOT');path.chmod(0o600);self.forbidden.append(path)
        for name,(_uid,_gid,files) in m.RUNTIME.items():
            directory=m.RUNTIME_ARCHIVE.parent/name;directory.mkdir(mode=0o700)
            for name in files:
                path=directory/name;path.write_bytes(b'INVENTED PRIVATE STAGING');path.chmod(0o440);self.forbidden.append(path)
        self.lock=m.lock_state();self.addCleanup(os.close,self.lock)
        self.binding=m.inventory(self.backend)[0]
        self.original_read=os.open
        def checked_open(path,*args,**kwargs):
            if isinstance(path,(str,Path)):
                candidate=Path(path)
                if candidate in self.forbidden + self.prior_forbidden:
                    self.fail('Helper opened private fixture contents')
            return self.original_read(path,*args,**kwargs)
        p=patch.object(m.os,'open',side_effect=checked_open);p.start();self.addCleanup(p.stop)

    @staticmethod
    def json(path,value):
        path.write_text(json.dumps(value)+'\n');path.chmod(0o600)

    def run_archive(self,binding=None):
        with patch.object(m,'verify_live'):
            return m.archive(self.backend,self.binding if binding is None else binding,self.lock)

    def test_probe_never_opens_private_contents_or_mutates(self):
        before={str(p):p.stat().st_ino for p in self.forbidden}
        observed=m.inventory(self.backend)[0]
        self.assertEqual(observed,self.binding)
        self.assertFalse(m.ARCHIVE.exists());self.assertFalse(m.RUNTIME_ARCHIVE.exists())
        self.assertEqual(before,{str(p):p.stat().st_ino for p in self.forbidden})

    def test_archive_preserves_snapshot_staging_and_existing_lock(self):
        before={str(p): (p.stat().st_ino,p.stat().st_mode,p.stat().st_nlink) for p in self.forbidden}
        lock_inode=os.fstat(self.lock).st_ino
        prior={str(p): (p.stat().st_ino,p.stat().st_size,p.stat().st_mode) for p in self.prior_forbidden}
        result=self.run_archive()
        self.assertEqual(prior,{str(p): (p.stat().st_ino,p.stat().st_size,p.stat().st_mode) for p in self.prior_forbidden})
        self.assertEqual(result['code'],'FIRST_RELEASE_ATTEMPT_ARCHIVED')
        self.assertEqual(list(p.name for p in m.STATE.iterdir()),['transaction.lock'])
        self.assertEqual((m.STATE/'transaction.lock').stat().st_ino,lock_inode)
        for name in m.FILES:self.assertTrue((m.ARCHIVE/name).is_file())
        for old,metadata in before.items():
            old=Path(old)
            if (m.STATE/'snapshot') in old.parents:new=m.ARCHIVE/old.relative_to(m.STATE)
            else:new=m.RUNTIME_ARCHIVE/old.relative_to(m.RUNTIME_ARCHIVE.parent)
            item=new.stat();self.assertEqual((item.st_ino,item.st_mode,item.st_nlink),metadata)
        self.assertFalse(m.GUARD.exists());self.assertFalse((m.VOLATILE/'masks.json').exists())
        self.assertEqual(self.backend.control.properties(self.foreign)['LoadState'],'masked')
        self.assertFalse(any('start' in cmd or 'stop' in cmd or 'restore' in cmd for cmd in self.commands))

    def test_phase_is_last_move_and_other_moves_are_durable_first(self):
        original=os.rename;events=[]
        def rename(source,target):
            if Path(source)==m.STATE/'phase.json':
                self.assertEqual(set(os.listdir(m.STATE)),{'transaction.lock','phase.json'})
                self.assertTrue((m.ARCHIVE/'snapshot/candidate-state-retained').is_dir())
                for name in m.RUNTIME:self.assertTrue((m.RUNTIME_ARCHIVE/name).is_dir())
            events.append(Path(source).name);return original(source,target)
        with patch.object(m.os,'rename',side_effect=rename):self.run_archive()
        self.assertEqual(events[-1],'phase.json')

    def test_foreign_archive_refused_without_replacement(self):
        m.ARCHIVE.mkdir();sentinel=m.ARCHIVE/'foreign';sentinel.write_bytes(b'KEEP')
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertEqual(sentinel.read_bytes(),b'KEEP');self.assertTrue((m.STATE/'phase.json').exists())

    def test_changed_binding_or_initial_refuses_before_any_archive(self):
        changed=copy.deepcopy(self.binding);changed['records']['initial.json']['sha256']='0'*64
        with self.assertRaises(m.Refused):self.run_archive(changed)
        self.assertFalse(m.ARCHIVE.exists())
        (m.STATE/'initial.json').write_text('{}')
        with self.assertRaises(Exception):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())

    def test_unknown_state_entry_refuses_without_cleanup(self):
        extra=m.STATE/'foreign';extra.write_bytes(b'KEEP')
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertEqual(extra.read_bytes(),b'KEEP');self.assertFalse(m.ARCHIVE.exists())

    def test_symlink_or_hardlink_metadata_refused(self):
        path=m.STATE/'phase.json';saved=path.read_bytes();path.unlink();path.symlink_to(m.RESULT)
        with self.assertRaises(OSError):self.run_archive()
        path.unlink();path.write_bytes(saved);path.chmod(0o600);os.link(path,self.base/'second-link')
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())

    def test_foreign_guard_target_refused(self):
        m.GUARD.unlink();m.GUARD.symlink_to('/foreign/guard')
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertEqual(os.readlink(m.GUARD),'/foreign/guard');self.assertFalse(m.ARCHIVE.exists())

    def test_concurrent_lock_is_refused_and_inode_retained(self):
        inode=os.fstat(self.lock).st_ino
        with self.assertRaises(BlockingIOError):m.lock_state()
        self.assertEqual((m.STATE/'transaction.lock').stat().st_ino,inode)

    def test_failure_mid_move_keeps_phase_and_all_data_in_one_of_two_locations(self):
        original=os.rename;calls=0
        def fail(source,target):
            nonlocal calls
            calls+=1
            if calls==6:raise OSError('INVENTED RENAME FAILURE')
            return original(source,target)
        with patch.object(m.os,'rename',side_effect=fail),self.assertRaises(OSError):self.run_archive()
        self.assertTrue((m.STATE/'phase.json').exists())
        for name in m.FILES:
            self.assertEqual(sum((folder/name).exists() for folder in (m.STATE,m.ARCHIVE)),1)
        for name in m.RUNTIME:
            self.assertEqual(sum((folder/name).exists() for folder in (m.RUNTIME_ARCHIVE.parent,m.RUNTIME_ARCHIVE)),1)
        with self.assertRaises(m.Refused):self.run_archive()

    def test_http_or_identity_live_refusal_has_no_effect(self):
        with patch.object(m,'verify_live',side_effect=m.Refused('FIXTURE')):
            with self.assertRaises(m.Refused):m.archive(self.backend,self.binding,self.lock)
        self.assertFalse(m.ARCHIVE.exists());self.assertFalse(m.RUNTIME_ARCHIVE.exists())

    def test_unexpected_runtime_member_or_public_permissions_refused(self):
        profile=next(iter(m.RUNTIME));directory=m.RUNTIME_ARCHIVE.parent/profile
        extra=directory/'unexpected';extra.write_bytes(b'KEEP')
        with self.assertRaises(m.Refused):self.run_archive()
        extra.unlink();directory.chmod(0o755)
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())

    def test_held_or_mismatched_result_refused(self):
        self.json(m.STATE/'phase.json',{'schema_version':1,'phase':m.Phase.HELD.value,'elapsed_seconds':0})
        with self.assertRaises(m.Refused):self.run_archive()
        self.json(m.STATE/'phase.json',{'schema_version':1,'phase':m.Phase.RETURNED.value,'elapsed_seconds':0})
        self.json(m.RESULT,{'schema_version':1,'code':'COHERENT_RETURN_REQUIRES_RECOVERY','phase':m.Phase.RETURNED.value})
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())

    def test_prior_archive_identity_change_or_bad_completion_refused(self):
        self.json(m.PRIOR_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'WRONG'})
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())
        self.json(m.PRIOR_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'FIRST_RELEASE_ATTEMPT_ARCHIVED'})
        m.PRIOR_RUNTIME_ARCHIVE.rename(self.base/'prior-retained-renamed')
        m.PRIOR_RUNTIME_ARCHIVE.mkdir(mode=0o700)
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())

    def test_controller_must_have_finished_before_any_move(self):
        good=self.backend.control.execute
        for raw in ('LoadState=loaded\nActiveState=active\nSubState=running\nMainPID=42\nExecMainCode=0\nExecMainStatus=0\n',
                    'LoadState=loaded\nActiveState=failed\nSubState=failed\nMainPID=0\nExecMainCode=1\nExecMainStatus=1\nForeign=private\n'):
            self.backend.control.execute=lambda *_args,**_kwargs:raw
            with self.assertRaises(m.Refused):m.controller_finished(self.backend)
        self.backend.control.execute=good
        m.controller_finished(self.backend)
        with patch.object(m,'verify_live',side_effect=m.Refused('FIXTURE')):
            with self.assertRaises(m.Refused):m.archive(self.backend,self.binding,self.lock)
        self.assertFalse(m.ARCHIVE.exists())

    def test_live_return_requires_old_profiles_free_ids_http_and_no_gate(self):
        with patch.object(m.os.path,'realpath',return_value=m.PREVIOUS), \
             patch.object(m.pwd,'getpwuid',side_effect=KeyError), \
             patch.object(m.grp,'getgrgid',side_effect=KeyError):
            m.verify_live(self.backend,self.units)
            with patch.object(m.os.path,'realpath',return_value='/invented/candidate'):
                with self.assertRaises(m.Refused):m.verify_live(self.backend,self.units)
            with patch.object(m.pwd,'getpwuid',return_value=object()):
                with self.assertRaises(m.Refused):m.verify_live(self.backend,self.units)
            with patch.object(self.backend,'previous_http',return_value={}):
                with self.assertRaises(m.Refused):m.verify_live(self.backend,self.units)
            good=self.backend.control.execute
            self.backend.control.execute=lambda args,**kw:0 if 'nft' in args[0] else good(args,**kw)
            with self.assertRaises(m.Refused):m.verify_live(self.backend,self.units)
            self.backend.control.execute=good
        self.assertFalse(m.ARCHIVE.exists())

    def test_exact_failure_bytes_inode_mode_and_digest_are_retained(self):
        path=m.STATE/'failure.json';raw=path.read_bytes();before=path.stat()
        self.assertEqual(self.binding['records']['failure.json']['sha256'],hashlib.sha256(raw).hexdigest())
        result=self.run_archive();retained=m.ARCHIVE/'failure.json';after=retained.stat()
        self.assertEqual(retained.read_bytes(),raw)
        self.assertEqual((before.st_dev,before.st_ino,before.st_mode,before.st_nlink),
                         (after.st_dev,after.st_ino,after.st_mode,after.st_nlink))
        self.assertTrue(result['failure_record_preserved'])
        self.assertEqual(set(self.binding['prior_archives']),{'001','002','003'})

    def test_foreign_failure_release_code_or_schema_refused_before_move(self):
        path=m.STATE/'failure.json';value=json.loads(path.read_bytes())
        for changed in ({**value,'release_sha256':'a'*64}, {**value,'schema_version':True},
                        {**value,'code':'HELPER_REFUSED'}, {**value,'component':'PRIVATE_UNKNOWN'},
                        {**value,'private':'DO_NOT_EXPORT'}):
            self.json(path,changed)
            with self.assertRaises(m.Refused):self.run_archive()
            self.assertFalse(m.ARCHIVE.exists())
        path.unlink()
        with self.assertRaises(m.Refused):self.run_archive()

    def test_pending_failure_publication_retained_and_refused(self):
        pending=m.STATE/'failure.json.next';pending.write_bytes(b'INCOMPLETE PRIVATE METADATA')
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertEqual(pending.read_bytes(),b'INCOMPLETE PRIVATE METADATA')
        self.assertFalse(m.ARCHIVE.exists())
        pending.unlink();os.link(m.STATE/'failure.json',pending)
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertEqual((m.STATE/'failure.json').stat().st_nlink,2)
        self.assertTrue(pending.exists())

    def test_failure_modified_after_probe_refused_even_if_schema_still_valid(self):
        path=m.STATE/'failure.json';value=json.loads(path.read_bytes())
        path.write_text(json.dumps(value,indent=2)+'\n')
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())

    def test_earlier_archive_change_refuses_without_touching_either_history(self):
        self.json(m.EARLIER_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'WRONG'})
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())
        self.assertTrue((m.PRIOR_ARCHIVE/'kept-private-snapshot').exists())


    def test_third_archive_change_or_missing_refuses_before_mutation(self):
        self.json(m.THIRD_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'WRONG'})
        with self.assertRaises(m.Refused):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())
        self.json(m.THIRD_ARCHIVE/'archive-complete.json',{'schema_version':1,'code':'FIRST_RELEASE_ATTEMPT_ARCHIVED'})
        m.THIRD_RUNTIME_ARCHIVE.rename(self.base/'third-retained-renamed')
        with self.assertRaises(FileNotFoundError):self.run_archive()
        self.assertFalse(m.ARCHIVE.exists())
        self.assertTrue((m.PRIOR_ARCHIVE/'kept-private-snapshot').exists())
        self.assertTrue((m.EARLIER_ARCHIVE/'kept-private-snapshot').exists())


if __name__=='__main__':unittest.main()
