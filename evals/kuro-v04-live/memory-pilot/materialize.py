from pathlib import Path
from sys import argv

root = Path(__file__).resolve().parent
sources = {'D': 'frozen/checkpoint.txt', 'Q': 'raw/g.txt', 'V': 'raw/h.txt'}
def cap(text, limit=900):
    stream = text.encode()
    if len(stream) <= limit:
        return text
    prefix = stream[:limit].decode('utf-8', errors='ignore')
    if len(stream) > limit and not prefix[-1].isspace() and not stream[limit:limit+1].isspace():
        prefix = prefix.rsplit(None, 1)[0] if any(c.isspace() for c in prefix) else ''
    return prefix.rstrip()
for code in argv[1:] or sources:
    content = (root / sources[code]).read_text().rstrip('\n')
    if code != 'D':
        content = cap(content)
    preamble = (root / 'frozen/receiver.txt').read_text().rstrip()
    (root / f'inputs/{code}.txt').write_text(preamble + '\n\n' + content + '\n')
