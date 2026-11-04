"""ViSe inventory coverage and additions, without reading application data."""
import json
from pathlib import Path
import unittest
import source_scope as S


class Scope(unittest.TestCase):
    def test_entire_previously_qualified_source_selection_is_covered(self):
        lock=json.loads((Path(__file__).resolve().parents[1]/'sources.lock.json').read_text())
        self.assertEqual(len(lock['files']),42)
        self.assertEqual([name for name in lock['files'] if not S.selected(name)],[])

    def test_new_code_and_assets_are_selected_without_a_frozen_file_count(self):
        for name in ['backend/src/routes/new.rs','backend/migrations/002.sql','backend/build.rs',
                     'backend/tests/integration.rs',
                     'bridge/new-worker.ts','frontend/src/New.elm','frontend/new-icon.webp',
                     'shared/elm/New.elm','shared/assets/new.css','content/new.json',
                     'scripts/new-build-step.mjs','tests/new.test.ts']:
            with self.subTest(name=name):self.assertTrue(S.selected(name))

    def test_private_runtime_outputs_and_dependency_trees_are_not_sources(self):
        for name in ['.env','backup/database.dump','deletions.log','target/release/server',
                     'dist/app.js','node_modules/a/index.js','frontend/token.key',
                     'backend/src/local.pem','content/user-data.sqlite',
                     '.git/config','operations/deploy.sh','README.org']:
            with self.subTest(name=name):self.assertFalse(S.selected(name))

    def test_paths_cannot_escape_or_alias_a_selected_root(self):
        for name in ['/backend/src/main.rs','backend/src/../../secret.rs',
                     'backend//src/main.rs','backend/src/./main.rs',
                     'backend\\src\\main.rs','bridge/main.ts\x00','bridge-extra/file.ts',None]:
            with self.subTest(name=name):self.assertFalse(S.selected(name))


if __name__=='__main__':unittest.main()
