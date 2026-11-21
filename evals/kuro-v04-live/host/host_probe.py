"""One synthetic local-thread probe of Codex app-server's public stdio protocol."""
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent
WORK = ROOT / 'work'
WORK.mkdir(exist_ok=True)
CLI = '/opt/codex/bin/codex'
MODEL = 'gpt-6.2-astra'
FIXTURE = 'id\tincoming\toutgoing\nMOSS-64\t148\t59\nIVY-03\t37\t15\n'
(WORK / 'entries.tsv').write_text(FIXTURE)
WORK_PROMPT = 'Read entries.tsv with a local read-only file tool and compute incoming minus outgoing for both records. Reply with each ID and its computed value, and nothing else. The audit was proposed only. Do not send anything or perform an audit.'
REPORT_PROMPT = 'From the work so far, report the two balances and the audit status in one sentence. Use only existing context for this report.'
started = time.monotonic()
log = {'cli': subprocess.check_output([CLI, '--version'], text=True).strip(), 'model_requested': MODEL,
       'speed_requested': 'default', 'work_prompt': WORK_PROMPT, 'report_prompt': REPORT_PROMPT,
       'fixture': FIXTURE, 'events': [], 'outcome': 'uncompleted'}
incoming = queue.Queue()
state = tempfile.TemporaryDirectory(prefix='codex-sqlite-', dir=ROOT)
proc = subprocess.Popen([CLI, 'app-server', '-c', 'sqlite_home='+json.dumps(state.name), '--listen', 'stdio://'], cwd=WORK, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)


def pump():
    for row in proc.stdout:
        try:
            incoming.put(json.loads(row))
        except ValueError:
            continue
    incoming.put(None)


threading.Thread(target=pump, daemon=True).start()


def event(name, **values):
    log['events'].append({'elapsed_s': round(time.monotonic()-started, 2), 'event': name, **values})


def send(method, params=None, ident=None):
    obj = {'jsonrpc': '2.0', 'method': method}
    if params is not None:
        obj['params'] = params
    if ident is not None:
        obj['id'] = ident
    proc.stdin.write(json.dumps(obj)+'\n')
    proc.stdin.flush()


def sanitize(message):
    message = str(message or '')
    # Only protocol/network diagnostics go to disk. Remove endpoint query/path, auth and filesystem details.
    message = re.sub(r'\b(?:https?|wss?)://([^/:?\s\)]+)[^\s\)]*', r'[endpoint \1]', message)
    message = re.sub(r'(?i)\b(?:bearer|basic)\s+[A-Za-z0-9_.+/-]+=*', '[redacted]', message)
    message = re.sub(r'(?i)(token|key|secret)[=:][^\s,;]+', r'\1=[redacted]', message)
    message = re.sub(r'\b(?:sk-|eyJ)[A-Za-z0-9_.-]+', '[redacted]', message)
    message = re.sub(r'/[^\s,\])]+', '[path]', message)
    return message[:500]


stderr_diagnostics = []


def drain_stderr():
    for line in proc.stderr:
        if re.search(r'(?i)error|failed|panic|denied|timeout|blocked|unavailable|refused|exited', line):
            # Do not retain full startup configuration or auth messages.
            if re.search(r'(?i)authorization:|cookie:|"access_token"|"refresh_token"', line):
                continue
            line = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
            stderr_diagnostics.append(sanitize(line))


stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
stderr_thread.start()


def receive(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Protocol wait exceeded its local deadline')
    try:
        item = incoming.get(timeout=remaining)
    except queue.Empty:
        raise TimeoutError('Protocol wait exceeded its local deadline') from None
    if item is None:
        raise RuntimeError('Local app-server closed the protocol stream')
    return item


stage = 'startup'


def note(item):
    method = item.get('method')
    params = item.get('params') or {}
    if method == 'error':
        err = params.get('error') or {}
        event('error', stage=stage, message=sanitize(err.get('message')), will_retry=params.get('willRetry'))
    elif method == 'item/completed':
        result = params.get('item') or {}
        kind = result.get('type')
        props = {'kind': kind, 'stage': stage}
        if kind == 'agentMessage':
            props['text'] = result.get('text','')[:1200]
        if kind == 'commandExecution':
            props['exit_code'] = result.get('exitCode')
            output = result.get('aggregatedOutput', '') or ''
            props['both_fixture_rows_in_output'] = all(x in output for x in ['MOSS-64', 'IVY-03'])
        event(method, **props)
    elif method == 'thread/tokenUsage/updated':
        event(method, stage=stage, usage=params.get('tokenUsage'))
    elif method in ['turn/started','turn/completed','thread/compacted']:
        turn = params.get('turn') or {}
        event(method, stage=stage, status=turn.get('status'), duration_ms=turn.get('durationMs'),
              error=sanitize((turn.get('error') or {}).get('message')))


def response(ident, seconds=25):
    deadline = time.monotonic()+seconds
    while True:
        item = receive(deadline)
        if 'method' in item:
            note(item)
            if 'id' in item:
                raise RuntimeError('Unexpected host-initiated request: '+str(item['method']))
        if item.get('id') == ident:
            if item.get('error'):
                raise RuntimeError(sanitize(item['error'].get('message')))
            return item.get('result', {})


def completion(seconds=48):
    deadline = time.monotonic()+seconds
    while True:
        item = receive(deadline)
        note(item)
        if 'method' in item and 'id' in item:
            raise RuntimeError('Unexpected host-initiated request: '+str(item['method']))
        if item.get('method') == 'turn/completed':
            status = item['params']['turn']['status']
            if status != 'completed':
                raise RuntimeError('Turn ended with status '+status)
            return


def turn(ident, prompt):
    send('turn/start',{'threadId': thread_id, 'input': [{'type':'text','text':prompt}], 'effort':'low',
                       'serviceTierForTurn':'default'},ident)
    response(ident)
    completion()


try:
    send('initialize', {'clientInfo': {'name':'synthetic_probe','version':'1.0'}},1)
    response(1)
    event('initialize response')
    stage = 'thread start'
    send('initialized')
    send('thread/start', {'model':MODEL, 'modelProvider':'openai','serviceTier':'default','ephemeral':True,
         'cwd':os.fspath(WORK), 'sandbox':'read-only','approvalPolicy':'never'},2)
    thread = response(2, 40)
    thread_id = thread['thread']['id']
    event('thread/start response', model=thread.get('model'), provider=thread.get('modelProvider'), tier=thread.get('serviceTier'))
    stage='work'
    turn(3,WORK_PROMPT)
    work_events = [e for e in log['events'] if e.get('stage')=='work']
    text = '\n'.join(e.get('text','') for e in work_events)
    if not (any(e.get('exit_code') == 0 and e.get('both_fixture_rows_in_output') for e in work_events)
            and all(v in text for v in ['MOSS-64','89','IVY-03','22'])):
        raise RuntimeError('Work evidence gate failed (successful fixture read plus expected balances)')
    stage='compaction'
    send('thread/compact/start',{'threadId':thread_id},4)
    response(4)
    completion()
    if not any(e.get('stage')=='compaction' and (e.get('kind')=='contextCompaction' or e['event']=='thread/compacted') for e in log['events']):
        raise RuntimeError('No host compaction completion signal')
    stage='report'
    turn(5,REPORT_PROMPT)
    if not any(e.get('stage')=='report' and e.get('kind')=='agentMessage' and e.get('text') for e in log['events']):
        raise RuntimeError('No post-compaction report observed')
    log['outcome']='post-compaction report observed'
except Exception as err:
    log['outcome']='incomplete'
    log['stop_stage']=stage
    log['reason']=sanitize(err)
finally:
    log['process_exit_before_cleanup'] = proc.poll()
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    stderr_thread.join(timeout=1)
    log['diagnostics']=stderr_diagnostics[-12:]
    state.cleanup()
    log['elapsed_s']=round(time.monotonic()-started,2)
    (ROOT/'host_observation.json').write_text(json.dumps(log,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(log,ensure_ascii=False,indent=2))
