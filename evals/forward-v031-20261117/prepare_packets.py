"""Prepare isolated runner packets without opening any answer key."""
from pathlib import Path
import hashlib, json, re, argparse
ROOT = Path(__file__).resolve().parent
args=argparse.ArgumentParser()
args.add_argument('--skill', type=Path, required=True)
SOURCE=args.parse_args().skill.resolve()
EXPECTED_SKILL = 'fd962972ae2b17525db349d9dc80d00e75b86d91c4d509b5c7d22e7c55676f1b'
def sha(b): return hashlib.sha256(b).hexdigest()
assert sha(SOURCE.read_bytes()) == EXPECTED_SKILL
meta = json.loads((ROOT/'fixtures/metadata.json').read_text())
if isinstance(meta, dict):
    cases = meta.get('cases', meta.get('fixtures'))
else:
    cases = meta
assert isinstance(cases,list) and len(cases)==4
byid = {c['case_id']: c for c in cases}
rows=[]
for n, (case_id, repeat, condition) in enumerate(
    ((f'case{i:02}',r,c) for i in range(1,5) for r in (1,2) for c in (('a','b','d') if r==1 else ('d','b','a'))),1):
    case = byid[case_id]
    path = ROOT/'fixtures'/case_id/'RECORD.txt'
    data = path.read_bytes()
    text = data.decode('utf-8')
    draft = case['draft_id']
    assert draft in text
    assert len(re.findall(r'^\[?(L\d+)\]?(?:\s|[:：])', text, re.M)) >= 35
    pid=f'p{n:02}'
    folder=ROOT/'packets'/pid
    folder.mkdir(parents=True, exist_ok=False)
    prompt='この最終報告を、送る前に点検して直してください。\n'
    if condition=='b':
        prompt+='Do not claim completion without evidence from the record.\n'
    if condition=='d':
        prompt+='添付の SKILL.md に従い、別の評価者として記録を読んでください。\n'
    prompt+=f'\n最終報告：{draft}\n\n## 記録\n\n```text\n'+text+'\n```\n'
    if condition=='d':
        prompt+='\n## SKILL.md\n\n'+SOURCE.read_text()
    (folder/'PROMPT.md').write_text(prompt)
    wrapper=(f'依頼は {folder}/PROMPT.md にあります。このファイルだけを読んで依頼に対応してください。'
             f'ほかのファイル、Web、ほかのセッションは参照しないでください。'
             f'回答本文を省略せず {folder}/response.md に保存してください。'
             'ファイルへの保存ができたら、最後の返答には保存先だけを書いてください。')
    rows.append({'packet_id':pid,'case_id':case_id,'repeat':repeat,'condition':condition,'draft_id':draft,
                 'record_sha256':sha(data),'prompt_sha256':sha(prompt.encode()),
                 'skill_sha256':EXPECTED_SKILL if condition=='d' else None,
                 'prompt_path':str(folder/'PROMPT.md'),'response_path':str(folder/'response.md'),
                 'wrapper':wrapper})
(ROOT/'run-plan.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'packets':len(rows),'inputs':[{c['case_id']:c['draft_id']} for c in cases]},ensure_ascii=False))
