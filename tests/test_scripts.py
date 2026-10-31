import os
from pathlib import Path
import subprocess
import sys
import json
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ScriptsTest(unittest.TestCase):
    def test_pinned_build_uses_private_cargo_state_and_drops_consumer_hooks(self):
        for mismatch in [False,True]:
            with self.subTest(mismatch=mismatch),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                commands=root/'commands';commands.mkdir()
                caller=root/'application';(caller/'.cargo').mkdir(parents=True)
                (caller/'.cargo/config.toml').write_text('[build]\nrustc-wrapper="application-sentinel"\n')
                pin=(ROOT/'ghenv-source').read_text().strip()
                git='''import sys
from pathlib import Path
if 'init' in sys.argv:Path(sys.argv[-1]).mkdir()
elif 'rev-parse' in sys.argv:print(PIN)
'''.replace('PIN',repr('0'*40 if mismatch else pin))
                cargo='''import os,sys
from pathlib import Path
assert sys.argv[1]=='build'
assert '--locked' in sys.argv and '--release' in sys.argv
assert 'GHENV_PREVIEW_BUNDLE' not in os.environ
assert 'RUSTC_WRAPPER' not in os.environ
assert 'CARGO_BUILD_RUSTC_WRAPPER' not in os.environ
assert Path.cwd().name=='source'
state=Path.cwd().parent
assert Path(os.environ['CARGO_HOME'])==state/'cargo-home'
assert os.environ['COMMIT']==PIN
target=Path(sys.argv[sys.argv.index('--target-dir')+1])
assert target==state/'target'
(target/'release').mkdir(parents=True)
binary=target/'release/ghenv';binary.write_text('synthetic exporter');binary.chmod(0o700)
'''.replace('PIN',repr(pin))
                rustup='import sys\nassert sys.argv[1:4]==["which","--toolchain","1.94.0"]\nprint('+repr(str(commands))+'+"/"+sys.argv[4])\n'
                for name,body in [('git',git),('cargo',cargo),('rustc',''),('rustup',rustup)]:
                    path=commands/name;path.write_text('#!'+sys.executable+'\n'+body);path.chmod(0o700)
                output=root/'outputs'
                env=dict(os.environ,RUNNER_OS='Linux',RUNNER_TEMP=str(root),GHENV_ACTION_PATH=str(ROOT),GHENV_ENVIRONMENT='Preview',GHENV_REQUEST_ID='a'*32,GHENV_PUBLIC_KEY='synthetic',GITHUB_OUTPUT=str(output),PATH=str(commands)+os.pathsep+os.environ['PATH'],GHENV_PREVIEW_BUNDLE='must-not-reach-build',RUSTC_WRAPPER='must-not-reach-build',CARGO_BUILD_RUSTC_WRAPPER='must-not-reach-build')
                result=subprocess.run(['bash',str(ROOT/'scripts/prepare.sh')],cwd=caller,env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode==0,not mismatch,result.stderr)
                state=Path(output.read_text().strip().removeprefix('state-dir='))
                if mismatch:self.assertFalse(state.exists())
                else:
                    self.assertEqual((state/'bin/ghenv').read_text(),'synthetic exporter')
                    self.assertEqual(state.stat().st_mode&0o777,0o700)
                    subprocess.run(['bash',str(ROOT/'scripts/cleanup.sh')],env=dict(env,GHENV_STATE_DIR=str(state)),check=True)
                    self.assertFalse(state.exists())

    def test_rust_probe_creates_only_synthetic_scoped_inputs(self):
        binary=Path(os.environ.get('CARGO_TARGET_DIR',str(ROOT/'target')))/'debug/ghenv-action-probe'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'outputs';output.touch()
            subprocess.run([str(binary.resolve()),'prepare'],env=dict(os.environ,RUNNER_TEMP=str(root),GITHUB_OUTPUT=str(output),GITHUB_REPOSITORY='owner/repo'),check=True)
            values=dict(line.split('=',1) for line in output.read_text().splitlines())
            self.assertRegex(values['request-id'],r'^[a-f0-9]{32}$')
            bundle=json.loads(values['bundle'])
            self.assertEqual(bundle['repository'],'owner/repo')
            self.assertEqual(bundle['environment'],'Preview')
            self.assertIn('UNREQUESTED',bundle['secrets'])
            self.assertEqual(json.loads(values['production-bundle'])['environment'],'Production')
            self.assertEqual((root/'ghenv-synthetic-private.der').stat().st_mode&0o777,0o600)

    def test_rejects_dispatch_input_before_install(self):
        for environment, request in [('Production', 'a' * 32), ('Preview', '$(touch marker)'), ('Preview', '../payload')]:
            with self.subTest(environment=environment, request=request), tempfile.TemporaryDirectory() as directory:
                env = dict(os.environ, RUNNER_OS='Linux', RUNNER_TEMP=directory,
                           GHENV_ACTION_PATH=str(ROOT), GHENV_ENVIRONMENT=environment,
                           GHENV_REQUEST_ID=request, GHENV_PUBLIC_KEY='synthetic',
                           GITHUB_OUTPUT=str(Path(directory) / 'outputs'))
                result = subprocess.run(['bash', str(ROOT / 'scripts/prepare.sh')], env=env,
                                        cwd=directory, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cleanup_refuses_outside_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'keep'
            marker.mkdir()
            env = dict(os.environ, RUNNER_TEMP=directory, GHENV_STATE_DIR=str(marker))
            result = subprocess.run(['bash', str(ROOT / 'scripts/cleanup.sh')], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(marker.exists())

    def test_cleanup_owned_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'ghenv-action.synthetic'
            state.mkdir()
            (state / 'payload.json').write_text('synthetic ciphertext')
            env = dict(os.environ, RUNNER_TEMP=directory, GHENV_STATE_DIR=str(state))
            subprocess.run(['bash', str(ROOT / 'scripts/cleanup.sh')], env=env, check=True)
            self.assertFalse(state.exists())

    def test_cleanup_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'ghenv-action.synthetic'
            state.mkdir()
            keep = Path(directory) / 'keep'
            keep.mkdir()
            env = dict(os.environ, RUNNER_TEMP=directory,
                       GHENV_STATE_DIR=str(state) + '/../keep')
            result = subprocess.run(['bash', str(ROOT / 'scripts/cleanup.sh')], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(keep.exists())


if __name__ == '__main__':
    unittest.main()
