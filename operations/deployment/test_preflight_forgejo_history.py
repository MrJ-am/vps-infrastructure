"""Real Git over invented bare repositories only; no network or VPS."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import preflight_forgejo_history as m

GIT = "/etc/profiles/per-user/jam/bin/git"


class HistoryProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)/"invented.git"
        self.env = {"HOME":"/nonexistent","LANG":"C","LC_ALL":"C","GIT_CONFIG_NOSYSTEM":"1",
                    "GIT_CONFIG_GLOBAL":"/dev/null","GIT_TERMINAL_PROMPT":"0","GIT_ALLOW_PROTOCOL":"file"}

    def git(self, *arguments, data=None):
        return subprocess.run([GIT,*arguments],input=data,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              env=self.env,check=True).stdout

    def inspect(self, commits=None):
        return m.inspect_repository(self.path,{"invented":"a"*40} if commits is None else commits,
                                    git=GIT, validate=lambda path:m.require(path.is_dir() and not path.is_symlink()),
                                    tree_validate=lambda path:m.historical_tree(path,owners=(0,os.getuid())))

    def test_absent_repository_never_executes_git(self):
        result=m.inspect_repository(self.path,{"invented":"a"*40},run=lambda *_a,**_k:self.fail("executed"))
        self.assertEqual(result["exists"],False)

    def test_empty_bare_repository_has_no_main_or_expected_commit(self):
        self.git("init","--bare","--initial-branch=main",str(self.path))
        result=self.inspect()
        self.assertEqual((result["exists"],result["bare"],result["non_empty"],result["main_exists"]),(True,True,False,False))
        self.assertEqual(result["expected_commits_present"],{"invented":False})

    def test_real_metadata_checks_never_return_authors_messages_or_refs(self):
        self.git("init","--bare","--initial-branch=main",str(self.path))
        tree=self.git("--git-dir="+str(self.path),"hash-object","-t","tree","-w","--stdin",data=b"").strip().decode()
        commit=self.git("-c","user.name=Invented Private Name","-c","user.email=invented@example.invalid",
                        "--git-dir="+str(self.path),"commit-tree",tree,data=b"INVENTED_PRIVATE_MESSAGE\n").strip().decode()
        self.git("--git-dir="+str(self.path),"update-ref","refs/heads/main",commit)
        result=self.inspect({"invented":commit,"absent":"a"*40})
        self.assertTrue(result["non_empty"])
        self.assertEqual(result["expected_commits_present"],{"invented":True,"absent":False})
        self.assertEqual(result["expected_commits_in_main"],{"invented":True,"absent":False})
        output=json.dumps(result)
        for forbidden in (commit,"Invented Private Name","INVENTED_PRIVATE_MESSAGE","refs/heads"):
            self.assertNotIn(forbidden,output)

    def test_alternates_promisors_or_symlink_never_trigger_external_object_reads(self):
        self.git("init","--bare","--initial-branch=main",str(self.path))
        alternate=self.path/"objects/info/alternates"
        alternate.write_text("/invented/outside\n")
        result=m.inspect_repository(self.path,{"invented":"a"*40},
            run=lambda *_a,**_k:self.fail("executed"),validate=lambda _:None,
            tree_validate=lambda path:m.historical_tree(path,owners=(0,os.getuid())))
        self.assertFalse(result["history_indirection_absent"])
        alternate.unlink()
        (self.path/"objects/pack/invented.promisor").write_text("")
        self.assertFalse(self.inspect()["history_indirection_absent"])
        link=Path(self.temporary.name)/"link.git"; link.symlink_to(self.path)
        self.path=link
        with self.assertRaises(ValueError):self.inspect()

    def test_pack_object_ref_or_config_link_refuses_before_git(self):
        self.git("init","--bare","--initial-branch=main",str(self.path))
        for suffix in ("objects/pack", "objects/invented", "refs/invented", "HEAD", "config", "packed-refs"):
            with self.subTest(suffix=suffix):
                target=self.path/suffix
                saved=target.with_name(target.name+"-saved")
                existed=target.exists()
                if existed:target.rename(saved)
                target.symlink_to("/invented-outside")
                with self.assertRaises(ValueError):
                    m.inspect_repository(self.path,{"invented":"a"*40},validate=lambda _:None,
                        tree_validate=lambda path:m.historical_tree(path,owners=(0,os.getuid())),
                        run=lambda *_a,**_k:self.fail("Git executed before link refusal"))
                target.unlink()
                if existed:saved.rename(target)


if __name__=="__main__":unittest.main()
