"""Offline release regression: exclusions, reproducibility, credentials and executable modes."""
import importlib.util
import json
import os
import shutil
import sys
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

spec=importlib.util.spec_from_file_location('release',Path(__file__).resolve().parents[1]/'scripts/prepare_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        subprocess.run(['git','init','-q'],cwd=self.root,check=True)
        (self.root/'.gitignore').write_text('data/\n')
    def tearDown(self):self.temp.cleanup()
    def write(self,name,content):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
    def test_source_excludes_runtime_and_saved_content(self):
        for name in ['.env','.env.local','.idea/workspace.xml','secrets/key.json','webapp/reports.json','webapp/analyses.json','cache.pem','bin/tool']:
            self.write(name,'excluded')
        self.write('app.py','print("demo")');self.write('scripts/start.sh','#!/bin/sh\nexit 0\n')
        archive,manifest=release.build_release(self.root)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(set(z.namelist()),{'dataleka/.gitignore','dataleka/app.py','dataleka/scripts/start.sh'})
            self.assertEqual((z.getinfo('dataleka/scripts/start.sh').external_attr>>16)&0o777,0o755)
        self.assertEqual(len(manifest['files']),3)
    def test_reproducible_and_credential_guard_covers_shell(self):
        self.write('app.py','demo')
        archive,a=release.build_release(self.root);first=archive.read_bytes()
        _,b=release.build_release(self.root)
        self.assertEqual(first,archive.read_bytes());self.assertEqual(a['sha256'],b['sha256'])
        fake='gh'+'p_'+'x'*36
        self.write('setup.sh',fake)
        with self.assertRaisesRegex(ValueError,'setup.sh') as error:release.build_release(self.root)
        self.assertNotIn(fake,str(error.exception))
        self.assertEqual(first,archive.read_bytes(),'Failed validation must preserve the previous archive')
    def test_symlinks_are_not_followed(self):
        with tempfile.TemporaryDirectory() as other:
            target=Path(other)/'private.txt';target.write_text('not source')
            (self.root/'alias.txt').symlink_to(target)
            archive,manifest=release.build_release(self.root)
            self.assertNotIn('alias.txt',manifest['files'])

class PublishTests(unittest.TestCase):
    def test_private_publish_verifies_commit_and_preserves_workspace(self):
        project=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'project';root.mkdir()
            remote=Path(folder)/'remote.git'
            (root/'scripts').mkdir();(root/'.venv/bin').mkdir(parents=True);(root/'bin').mkdir()
            for name in ['prepare_release.py','publish_github.sh']:
                shutil.copy(project/'scripts'/name,root/'scripts'/name)
            (root/'.venv/bin/python').symlink_to(sys.executable)
            (root/'.gitignore').write_text('data/\nbin/\n.venv/\n')
            (root/'README.md').write_text('Offline publish fixture')
            subprocess.run(['git','init','-q'],cwd=root,check=True)
            subprocess.run(['git','remote','add','origin','https://example.invalid/original'],cwd=root,check=True)
            before=subprocess.check_output(['git','status','--porcelain'],cwd=root)
            fake=root/'bin/gh'
            fake.write_text("""#!/usr/bin/env python3
import os,sys,subprocess
from pathlib import Path
args=sys.argv[1:]
if args[:2]==['auth','status']:sys.exit(0)
if args[:2]==['api','user']:
 print('fixture-user' if args[-1]=='.login' else '12345');sys.exit(0)
if args[:2]==['repo','create']:
 assert args[2]=='fixture-user/dataleka' and '--private' in args and '--push' in args
 source=args[args.index('--source')+1];remote=os.environ['PUBLISH_FIXTURE_REMOTE']
 subprocess.run(['git','init','--bare','-q',remote],check=True)
 subprocess.run(['git','-C',source,'remote','add','origin',remote],check=True)
 subprocess.run(['git','-C',source,'push','-q','origin','main'],check=True)
 Path(os.environ['PUBLISH_FIXTURE_PROOF']).write_text('PRIVATE dataleka')
 sys.exit(0)
if args[:2]==['repo','view']:
 print('https://example.invalid/fixture-user/dataleka');sys.exit(0)
raise SystemExit('Unexpected gh operation')
""")
            fake.chmod(0o755)
            env={**os.environ,'PATH':str(root/'bin')+os.pathsep+os.environ['PATH'],
                 'PUBLISH_FIXTURE_REMOTE':str(remote),'PUBLISH_FIXTURE_PROOF':str(Path(folder)/'proof')}
            result=subprocess.run(['bash','scripts/publish_github.sh'],cwd=root,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('Verified main commit:',result.stdout)
            self.assertEqual((Path(folder)/'proof').read_text(),'PRIVATE dataleka')
            self.assertEqual(before,subprocess.check_output(['git','status','--porcelain'],cwd=root))
            self.assertEqual(subprocess.check_output(['git','remote','get-url','origin'],cwd=root).decode().strip(),'https://example.invalid/original')
            self.assertTrue(subprocess.check_output(['git','--git-dir',str(remote),'rev-parse','refs/heads/main']).strip())

if __name__=='__main__':unittest.main(verbosity=2)
