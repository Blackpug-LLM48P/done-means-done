"""Freeze run outputs; does not read answer key bodies."""
from pathlib import Path
import hashlib,json,datetime,shutil
R=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
plan=json.loads((R/'run-plan.json').read_text())
assert len(plan)==24
out=[]
for row in plan:
    packet=Path(row['prompt_path'])
    response=Path(row['response_path'])
    assert sha(packet.read_bytes())==row['prompt_sha256'],f'packet changed: {packet}'
    assert response.is_file() and response.stat().st_size>0,f'missing/empty {response}'
    raw=response.read_bytes()
    raw.decode('utf-8')
    destination=R/'fixtures'/row['case_id']/'runs'/f"2026-11-17_host-model_{row['condition']}_r{row['repeat']}.md"
    destination.parent.mkdir(exist_ok=True)
    if destination.exists(): assert destination.read_bytes()==raw,'would overwrite differing frozen output'
    else: shutil.copyfile(response,destination)
    out.append({**row,'frozen_path':str(destination.relative_to(R)),'output_sha256':sha(raw),'output_bytes':len(raw),'output_characters':len(raw.decode('utf-8'))})
manifest={'captured_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_commit':'2fe38b0e0d94c3dc89adabc9146b145953fb467b','protocol_commit':'6d6776e034da91a1e1739af33cdd76a9b0a2966e','protocol_sha256':sha((R/'PROTOCOL.md').read_bytes()),'scoring_instructions_sha256':sha((R/'SCORING_INSTRUCTIONS.md').read_bytes()),'fixture_metadata_sha256':sha((R/'fixtures/metadata.json').read_bytes()),'keys_opened_by_orchestrator':False,'runs':out}
(R/'frozen-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'frozen_outputs':len(out),'manifest_sha256':sha((R/'frozen-manifest.json').read_bytes())}))
