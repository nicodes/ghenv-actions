import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ScriptsTest(unittest.TestCase):
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
