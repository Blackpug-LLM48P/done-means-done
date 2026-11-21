from pathlib import Path
from hashlib import sha256

root = Path(__file__).resolve().parents[1]
fixed = root / 'frozen'
source = (fixed / 'checkpoint.txt').read_text()
for record in ('g', 'h'):
    pieces = [(fixed / 'maintain_common.txt').read_text(),
              (fixed / f'maintain_{record}.txt').read_text(), source]
    (root / 'inputs' / f'{record}.txt').write_text('\n'.join(x.rstrip() for x in pieces) + '\n')
fixed_files = sorted(fixed.glob('*'))
(root / 'freeze.sha256').write_text(''.join(
    f'{sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n'
    for p in fixed_files if p.is_file()
))
