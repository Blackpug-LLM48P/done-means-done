"""Offline Codex host integration with fixed loopback Responses events, no model.

Run as `unshare -Urn python -B host_integration.py` on Linux. The script requires a
network namespace with only lo. Its temporary CLI home and environment contain no
ChatGPT credentials or API keys. Output intentionally omits full request bodies.
"""
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import socket
import shutil
import struct
import subprocess
import tempfile
import threading
import time

CLI = shutil.which('codex')
if CLI is None:
    raise SystemExit('The Codex CLI must be on PATH')
MARKER = 'COMPACT-TEAL-496'
BEFORE = 'BEFORE-BRASS-512'
OUTPUT = { 'cli': subprocess.check_output([CLI,'--version'],text=True).strip(), 'provider':'fixed local Responses stub',
           'ephemeral_thread':True, 'protocol':[], 'provider_requests':[] }

# A new user+network namespace provides private loopback and zero external interfaces.
interfaces = [line.split(':',1)[0].strip() for line in Path('/proc/net/dev').read_text().splitlines() if ':' in line]
if sorted(interfaces) != ['lo']:
    raise SystemExit('Requires unshare -Urn; found external network interfaces')
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
    flags_raw = fcntl.ioctl(control, 0x8913, struct.pack('16sH22x',b'lo',0))
    flags = struct.unpack('16sH22x',flags_raw)[1]
    fcntl.ioctl(control, 0x8914, struct.pack('16sH22x',b'lo',flags|1))
OUTPUT['network_interfaces']=['lo']
phase='initialize'


class FixedProvider(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        request=json.loads(body)
        inputs=json.dumps(request.get('input', []), ensure_ascii=False)
        OUTPUT['provider_requests'].append({'phase':phase, 'path':self.path,
            'pre_turn_assistant_marker_in_input':BEFORE in inputs,
            'stub_summary_marker_in_input':MARKER in inputs})
        if self.path != '/v1/responses':
            self.send_error(404); return
        answer={'before':BEFORE,'compact':MARKER,'after':'AFTER-SLATE-073'}.get(phase,'unexpected phase')
        ident='resp_'+phase
        msg={'id':'msg_'+phase,'type':'message','role':'assistant','status':'completed',
             'content':[{'type':'output_text','text':answer,'annotations':[]}]}
        basic={'id':ident,'object':'response','created_at':1,'status':'in_progress','model':'fixture-stub', 'output':[]}
        events=[{'type':'response.created','response':basic},
                {'type':'response.output_item.added','output_index':0,'item':dict(msg,status='in_progress',content=[])},
                {'type':'response.content_part.added','output_index':0,'content_index':0,'item_id':msg['id'],'part':{'type':'output_text','text':'','annotations':[]}},
                {'type':'response.output_text.delta','output_index':0,'content_index':0,'item_id':msg['id'],'delta':answer},
                {'type':'response.output_text.done','output_index':0,'content_index':0,'item_id':msg['id'],'text':answer},
                {'type':'response.output_item.done','output_index':0,'item':msg},
                {'type':'response.completed','response':dict(basic,status='completed',output=[msg])}]
        content=''.join('data: '+json.dumps(dict(evt,sequence_number=i))+'\n\n' for i,evt in enumerate(events)).encode()
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)


server=ThreadingHTTPServer(('127.0.0.1',0),FixedProvider)
threading.Thread(target=server.serve_forever,daemon=True).start()
started=time.monotonic()
with tempfile.TemporaryDirectory(prefix='fixture-') as scratch:
    work=Path(scratch)/'work'; work.mkdir()
    home=Path(scratch)/'codex'; home.mkdir()
    settings=f'''model="fixture-stub"
model_provider="offline_fixture"
project_doc_max_bytes=0
[model_providers.offline_fixture]
name="Fixed loopback fixture"
base_url="http://127.0.0.1:{server.server_port}/v1"
wire_api="responses"
requires_openai_auth=false
supports_websockets=false
request_max_retries=0
stream_max_retries=0
'''
    (home/'config.toml').write_text(settings)
    env={'HOME':str(Path(scratch)), 'CODEX_HOME':str(home),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    proc=subprocess.Popen([CLI,'app-server','--stdio'],cwd=work,env=env,stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
    pending=queue.Queue(); thread_id=None
    def read():
        for line in proc.stdout:
            try:
                pending.put(json.loads(line))
            except ValueError:
                pass
        pending.put(None)
    threading.Thread(target=read,daemon=True).start()
    def send(method,params,ident=None):
        obj={'method':method,'params':params}
        if ident is not None: obj['id']=ident
        proc.stdin.write(json.dumps(obj)+'\n'); proc.stdin.flush()
    def until(predicate,max_sec=20):
        stop=time.monotonic()+max_sec
        while True:
            try: obj=pending.get(timeout=max(.01,stop-time.monotonic()))
            except queue.Empty: raise TimeoutError('no matching host event') from None
            if obj is None: raise RuntimeError('host closed stream')
            method=obj.get('method'); params=obj.get('params') or {}; item=params.get('item') or {}; turn=params.get('turn') or {}
            if method in ['turn/started','turn/completed','item/started','item/completed','thread/compacted','error']:
                event={'phase':phase,'method':method}
                if item: event['kind']=item.get('type')
                if turn: event['status']=turn.get('status')
                if method=='error': event['message']=(params.get('error') or {}).get('message','')[:240]
                if method=='item/completed' and item.get('type')=='agentMessage': event['assistant_text']=item.get('text','')[:200]
                OUTPUT['protocol'].append(event)
            if predicate(obj): return obj
            if time.monotonic()>=stop: raise TimeoutError('no matching host event')
    def response(ident):
        obj=until(lambda x:x.get('id')==ident)
        if 'error' in obj: raise RuntimeError('protocol error: '+str(obj['error'].get('message',''))[:240])
        return obj['result']
    def complete():
        turn=until(lambda x:x.get('method')=='turn/completed')['params']['turn']
        if turn['status']!='completed': raise RuntimeError('host turn '+turn['status'])
    def input_turn(ident,text):
        send('turn/start',{'threadId':thread_id,'input':[{'type':'text','text':text}]},ident)
        response(ident); complete()
    try:
        send('initialize',{'clientInfo':{'name':'offline_integration','version':'1'}},1); response(1); send('initialized',{})
        phase='thread start'
        send('thread/start',{'model':'fixture-stub','modelProvider':'offline_fixture','ephemeral':True,'cwd':str(work),
                            'baseInstructions':'This is a local protocol fixture. Use plain text replies.',
                            'sandbox':'read-only','approvalPolicy':'never'},2)
        info=response(2); thread_id=info['thread']['id']; OUTPUT['host_provider']=info['modelProvider']; OUTPUT['host_model']=info['model'];
        phase='before'; input_turn(3,'First synthetic turn. Return the fixed reply.')
        phase='compact'; send('thread/compact/start',{'threadId':thread_id},4); response(4); OUTPUT['compact_request_accepted']=True; complete()
        phase='after'; input_turn(5,'Final synthetic turn. Return the fixed reply.')
        compacted=any(e['phase']=='compact' and (e.get('method')=='thread/compacted' or (e.get('method')=='item/completed' and e.get('kind')=='contextCompaction')) for e in OUTPUT['protocol'])
        after_marker=any(x['phase']=='after' and x['stub_summary_marker_in_input'] for x in OUTPUT['provider_requests'])
        before_in_after=any(x['phase']=='after' and x['pre_turn_assistant_marker_in_input'] for x in OUTPUT['provider_requests'])
        OUTPUT['checks']={'host_compaction_completion':compacted, 'summary_marker_reaches_next_provider_request':after_marker, 'prior_assistant_marker_absent_after':not before_in_after}
        OUTPUT['outcome']='integration observed' if all(OUTPUT['checks'].values()) else 'partial'
    except Exception as e:
        OUTPUT['outcome']='incomplete'; OUTPUT['stopped_at']=phase; OUTPUT['reason']=str(e)
    finally:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait()
server.shutdown(); server.server_close()
OUTPUT['harness_elapsed_s']=round(time.monotonic()-started,2)
print(json.dumps(OUTPUT,indent=2))
raise SystemExit(0 if OUTPUT['outcome'] == 'integration observed' else 1)
