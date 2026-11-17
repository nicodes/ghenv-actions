"""Check each independently installed handoff example with the shared rules."""
import os
from pathlib import Path
import runpy

import yaml

root = Path(__file__).resolve().parents[2]
checker = runpy.run_path(str(Path(os.environ['TOOLS_ROOT']) / 'helpers/workflow-names.py'))
paths = sorted((root / 'examples').rglob('*.yml'))
if not paths:
    raise ValueError('handoff examples are required')
for path in paths:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576:
        raise ValueError('workflow examples must be bounded regular source files')
    # Alternatives install separately under the same canonical workflow name.
    checker['validate']({path.relative_to(root).as_posix(): yaml.safe_load(path.read_text())})
print(f'Checked {len(paths)} alternative workflow examples.')
