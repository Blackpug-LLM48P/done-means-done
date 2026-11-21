"""Fallback using Codex's native noninteractive entry point and the existing login."""
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parent
prompt = json.loads((root/'host_observation.json').read_text())['work_prompt']
started = time.monotonic()
with tempfile.TemporaryDirectory(prefix='ephemeral-state-',dir=root) as state:
    opts = ['-c','sqlite_home='+json.dumps(state), '-c','log_dir='+json.dumps(state), '-c','service_tier="default"']
    cmd = ['/opt/codex/bin/codex','exec','--ephemeral','--json','--skip-git-repo-check','-s','read-only','-m','gpt-6.2-astra',*opts,prompt]
    try:
        result = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,cwd=root/'work',text=True,timeout=48)
        rows = []
        for line in result.stdout.splitlines():
            try:
                data=json.loads(line)
            except ValueError:
                continue
            entry={'type':data.get('type')}
            if data.get('usage'):
                entry['usage']=data['usage']
            if (data.get('item') or {}).get('type')=='agent_message':
                entry['text']=data['item'].get('text','')[:800]
            rows.append(entry)
        messages = []
        for line in (result.stderr+'\n'+result.stdout).splitlines():
            if any(word in line.lower() for word in ['error','failed','forbidden','closed','unavailable','disconnected','timed out','timeout']):
                if re.search(r'(?i)authorization:|cookie:|access_token|refresh_token|bearer\s+',line):
                    continue
                line = re.sub(r'\b(?:https?|wss?)://([^/:?\s\)]+)[^\s\)]*',r'[endpoint \1]',line)
                line = re.sub(r'/[^\s,\])]+','[path]',line)
                line = re.sub(r'\b(?:sk-|eyJ)[A-Za-z0-9_.-]+','[redacted]',line)
                messages.append(line.strip()[:380])
        out={'exit':result.returncode,'events':rows,'diagnostics':messages[-8:]}
    except subprocess.TimeoutExpired:
        out={'exit':None,'timeout_s':48}
out['elapsed_s']=round(time.monotonic()-started,2)
(root/'exec_observation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
