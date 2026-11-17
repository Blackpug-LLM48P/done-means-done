"""Run only after output-freeze commit. Creates masked copies, retaining raw outputs."""
from pathlib import Path
import json,hashlib,shutil,datetime
R=Path(__file__).resolve().parent
manifest=json.loads((R/'frozen-manifest.json').read_text())
assert (R/'freeze-commit.txt').is_file(), 'Commit the outputs before opening keys.'
metadata=json.loads((R/'fixtures/metadata.json').read_text())
checks=[]
for case in metadata:
    for kind,name in (('record','RECORD.txt'),('key','KEY.md')):
        raw=(R/'fixtures'/case['case_id']/name).read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        assert digest==case[kind+'_sha256'], f"{kind} changed: {case['case_id']}"
        checks.append({'case_id':case['case_id'],'kind':kind,'sha256':digest,'match':True})
(R/'key-opening.json').write_text(json.dumps({'opened_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeze_commit':(R/'freeze-commit.txt').read_text().strip(),'checks':checks},indent=2)+'\n')
out=R/'scoring-packets'
out.mkdir(exist_ok=True)
mapping={}
for case in ('case01','case02','case03','case04'):
    d=out/case;d.mkdir(exist_ok=True)
    shutil.copyfile(R/'fixtures'/case/'RECORD.txt',d/'RECORD.txt')
    shutil.copyfile(R/'fixtures'/case/'KEY.md',d/'KEY.md')
for run in manifest['runs']:
    code='S'+hashlib.sha256(('blind-score-v1:'+run['packet_id']).encode()).hexdigest()[:10]
    raw=(R/run['frozen_path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==run['output_sha256']
    (out/run['case_id']/(code+'.md')).write_bytes(raw)
    mapping[code]={k:run[k] for k in ('packet_id','case_id','repeat','condition','output_sha256')}
(R/'scoring-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
print(json.dumps({'masked_outputs':len(mapping),'case_dirs':4}))
