"""Exercise existing compiled consumer fixtures, not replacement toy pages."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import tempfile
import unittest
from fontTools.ttLib import TTFont
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ci/continuous-delivery-v1'))
import consumer_identity as C
import parisienne as P
import resources as R

sys.path.insert(0,os.environ['SIGNATURE_ASSEMBLY'])
import frontend_assembly as A


class Consumers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive={}
        with tarfile.open(os.environ['SIGNATURE_FRONTENDS']) as tar:
            for entry in tar:
                path=PurePosixPath(entry.name)
                if entry.isdir():
                    continue
                assert entry.isfile() and not path.is_absolute() and '..' not in path.parts
                assert entry.name not in cls.archive and entry.size<=16*1024**2
                cls.archive[entry.name]=tar.extractfile(entry).read()
        source=Path(os.environ['SIGNATURE_CAPTURE'])
        cls.resources={name:(source/origin).read_bytes() for name,origin in R.RESOURCES.items()}
        cls.resources['Parisienne-Regular.woff2'],cls.conversion=P.convert(cls.resources['Parisienne-Regular.ttf'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.revision='17194087eec9162bb5372221c43e1de0501dfe6a'

    def site(self,name):
        site=self.root/name;site.mkdir()
        for path,raw in self.archive.items():
            if not path.startswith(name+'/') or path==name+'/artifact.json':
                continue
            out=self.root/path;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
        return site

    def apply(self,site,name,resources=None):
        return C.apply(site,name,self.revision,resources or self.resources,version_mateval=A.version_mateval)

    def test_all_existing_consumers_keep_paths_and_final_manifests(self):
        for name in (*C.EXTRA,'style-logo'):
            with self.subTest(frontend=name):
                site=self.site(name)
                before={str(p.relative_to(site)):p.read_bytes() for p in site.rglob('*') if p.is_file()}
                result=self.apply(site,name)
                after={str(p.relative_to(site)):p.read_bytes() for p in site.rglob('*') if p.is_file()}
                self.assertLessEqual(set(before),set(after))
                self.assertFalse(result['deployment_authorized'])
                if name=='style-logo':
                    self.assertEqual(before,after)
                else:
                    for prefix in ('','admin/') if name=='mateval' else ('',):
                        for resource in C.BASE+C.EXTRA[name]:
                            self.assertEqual(after[prefix+'assets/mrjam/'+resource],self.resources[resource])
                        self.assertEqual(after[prefix+'assets/mrjam/Parisienne-OFL.txt'],self.resources['Parisienne-OFL.txt'])
                if name=='vision':
                    manifest=json.loads(after['manifest.json'])
                    self.assertEqual(manifest['revisionSignature'],self.revision)
                    self.assertEqual(manifest['fichiers'],{p:C.sha(raw) for p,raw in after.items() if p!='manifest.json'})
                if name=='mateval':
                    self.assertEqual(json.loads(after['interface.json'])['signature'],self.revision)
                    for prefix in ('','admin/'):
                        for metadata in ('identite.json','polices.json'):
                            path=prefix+'assets/mrjam/'+metadata
                            self.assertEqual(json.loads(after[path])['revision'],self.revision)
                            self.assertEqual(json.loads(after[path])['droits'],json.loads(before[path])['droits'])
                # Final runtime manifest must bind all new resources and the
                # selected Signature commit, using the actual canonical writer.
                A.runtime_manifest(site,name,{'signature':self.revision},'1'*40,'2'*64,'3'*64)
                manifest=json.loads((site/'artifact.json').read_bytes())
                self.assertEqual(manifest['payload_sha256'],{p:C.sha(raw) for p,raw in after.items()})
                self.assertEqual(manifest['source_commits']['signature'],self.revision)

    def test_mateval_css_urls_follow_changed_bytes(self):
        # This tests assembly, not permission to use these deliberately altered
        # bytes; the independent regeneration gate would reject this fixture.
        resources=dict(self.resources);resources['signature.css']+=b'\n/* fixture */\n'
        site=self.site('mateval');test_page=(site/'test.html').read_bytes()
        self.apply(site,'mateval',resources)
        expected=C.sha(resources['signature.css'])[:12]
        for name in ('index.html','enquete.html','prototype.html','admin/index.html'):
            urls=re.findall(r'assets/mrjam/signature\.css\?v=([0-9a-f]{12})',(site/name).read_text())
            self.assertTrue(urls,name);self.assertEqual(set(urls),{expected})
        # The existing minimal overlay page has no signature stylesheet.
        self.assertEqual((site/'test.html').read_bytes(),test_page)

    def test_existing_artifact_cannot_be_overwritten(self):
        site=self.site('log');(site/'artifact.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'SIGNATURE_ALREADY_MANIFESTED'):
            self.apply(site,'log')

    def test_symlink_resource_refused_before_writes(self):
        site=self.site('vision');p=site/'assets/mrjam/EchoPoint.woff2'
        p.unlink();p.symlink_to('/etc/passwd')
        old=(site/'assets/mrjam/signature.css').read_bytes()
        with self.assertRaisesRegex(ValueError,'SIGNATURE_ASSET_LINK_REFUSED'):
            self.apply(site,'vision')
        self.assertEqual((site/'assets/mrjam/signature.css').read_bytes(),old)

    def test_missing_existing_font_is_not_silently_added(self):
        site=self.site('log');(site/'assets/mrjam/EchoPoint.woff2').unlink()
        with self.assertRaises(FileNotFoundError):
            self.apply(site,'log')

    def test_parisienne_conversion_is_deterministic(self):
        second,_=P.convert(self.resources['Parisienne-Regular.ttf'])
        self.assertEqual(second,self.resources['Parisienne-Regular.woff2'])

    def test_parisienne_changed_metric_is_refused(self):
        with TTFont(io.BytesIO(self.resources['Parisienne-Regular.woff2']),recalcTimestamp=False) as font:
            name=font.getBestCmap()[ord('M')];advance,bearing=font['hmtx'][name]
            font['hmtx'][name]=(advance+1,bearing)
            output=io.BytesIO();font.save(output)
        with self.assertRaisesRegex(ValueError,'PARISIENNE_TABLE_CHANGED: hmtx'):
            P.equivalent(self.resources['Parisienne-Regular.ttf'],output.getvalue())

    def test_parisienne_changed_outline_is_refused(self):
        with TTFont(io.BytesIO(self.resources['Parisienne-Regular.woff2']),recalcTimestamp=False) as font:
            glyph=font['glyf'][font.getBestCmap()[ord('M')]]
            x,y=glyph.coordinates[0];glyph.coordinates[0]=(x+1,y)
            output=io.BytesIO();font.save(output)
        with self.assertRaisesRegex(ValueError,'PARISIENNE_OUTLINE_CHANGED|PARISIENNE_GLYPH_BOUNDS_CHANGED'):
            P.equivalent(self.resources['Parisienne-Regular.ttf'],output.getvalue())

    def test_parisienne_changed_hints_are_refused(self):
        with TTFont(io.BytesIO(self.resources['Parisienne-Regular.woff2']),recalcTimestamp=False) as font:
            glyph=font['glyf'][font.getBestCmap()[ord('M')]]
            code=bytearray(glyph.program.getBytecode());code.append(0)
            glyph.program.fromBytecode(code)
            output=io.BytesIO();font.save(output)
        with self.assertRaisesRegex(ValueError,'PARISIENNE_INSTRUCTIONS_CHANGED|PARISIENNE_TABLE_CHANGED: maxp'):
            P.equivalent(self.resources['Parisienne-Regular.ttf'],output.getvalue())


if __name__=='__main__':
    unittest.main()
