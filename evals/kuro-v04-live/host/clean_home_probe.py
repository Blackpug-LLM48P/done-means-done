"""Check whether the CLI supports initialization and inherited ChatGPT login in a new home."""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

root = Path(__file__).resolve().parent
cli = '/opt/codex/bin/codex'
result = {}
started = time.monotonic()
with tempfile.TemporaryDirectory(prefix='fresh-codex-state-', dir=root) as fresh_state_directory:
    # This is the CLI's own configuration home for these child processes only.
    # The directory starts empty. No identity or configuration file is transferred.
    cli_environment = os.environ.copy()
    cli_environment['CODEX_HOME'] = fresh_state_directory
    auth = subprocess.run([cli, 'login', 'status'], stdin=subprocess.DEVNULL, capture_output=True,
                          cwd=root/'work', env=cli_environment, text=True, timeout=12)
    status = (auth.stdout+' '+auth.stderr).strip()
    result['login_exit'] = auth.returncode
    result['login_status'] = ('ChatGPT' if 'Logged in using ChatGPT' in status else
                              'Not logged in' if 'Not logged in' in status else 'Other')
    app = subprocess.Popen([cli,'app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, env=cli_environment, text=True, cwd=root/'work')
    incoming = queue.Queue()
    def reader():
        for line in app.stdout:
            try:
                incoming.put(json.loads(line))
            except ValueError:
                continue
        incoming.put(None)
    threading.Thread(target=reader, daemon=True).start()
    try:
        app.stdin.write(json.dumps({'id':1,'method':'initialize','params':{'clientInfo':{
            'name':'synthetic_init_check','version':'1'}}})+'\n'); app.stdin.flush()
        stop=time.monotonic()+18
        while time.monotonic()<stop:
            obj=incoming.get(timeout=max(.01,stop-time.monotonic()))
            if obj is None:
                result['initialize']='stream closed'
                break
            if obj.get('id')==1:
                result['initialize']='success' if 'result' in obj else 'protocol error'
                break
    except queue.Empty:
        result['initialize']='timeout'
    finally:
        app.terminate()
        try:
            app.wait(timeout=3)
        except subprocess.TimeoutExpired:
            app.kill(); app.wait()
    result['elapsed_s']=round(time.monotonic()-started,2)
(root/'clean_home_observation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
