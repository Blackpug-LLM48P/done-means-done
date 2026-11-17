"""Check frozen skill-condition ledgers without opening answer keys."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,datetime
p=argparse.ArgumentParser();p.add_argument('--checker',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parent
assert (r/'freeze-commit.txt').is_file(), 'Freeze outputs before verification.'
m=json.loads((r/'frozen-manifest.json').read_text())
out=r/'quote-checks';out.mkdir(exist_ok=True)
results=[]
for run in m['runs']:
 if run['condition']!='d':continue
 ledger=r/run['frozen_path'];record=r/'fixtures'/run['case_id']/'RECORD.txt'
 assert hashlib.sha256(ledger.read_bytes()).hexdigest()==run['output_sha256']
 cmd=[sys.executable,str(a.checker.resolve()),'--draft',run['draft_id'],str(ledger),str(record)]
 done=subprocess.run(cmd,text=True,capture_output=True)
 text=done.stdout+('\nSTDERR:\n'+done.stderr if done.stderr else '')
 (out/(run['packet_id']+'.txt')).write_text(text)
 results.append({'packet_id':run['packet_id'],'case_id':run['case_id'],'repeat':run['repeat'],'draft_id':run['draft_id'],'command':cmd,'exit_code':done.returncode,'stdout':done.stdout,'stderr':done.stderr})
report={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checker_sha256':hashlib.sha256(a.checker.read_bytes()).hexdigest(),'python':sys.version,'runs':results,'keys_opened_by_this_script':False}
(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps([{'packet_id':v['packet_id'],'exit_code':v['exit_code']} for v in results]))
