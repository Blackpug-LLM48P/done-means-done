from pathlib import Path
import json,csv,hashlib,statistics
R=Path(__file__).resolve().parent
mapping=json.loads((R/'scoring-map.json').read_text())
manifest=json.loads((R/'frozen-manifest.json').read_text())
by_packet={x['packet_id']:x for x in manifest['runs']}
scores={};validation=[]
for who in ('alpha','beta'):
 items={}
 for p in sorted((R/f'scores-{who}').glob('case*.json')):
  obj=json.loads(p.read_text());assert len(obj['outputs'])==6
  for v in obj['outputs']:
   assert mapping[v['id']]['case_id']==obj['case_id'];assert v['id'] not in items
   for k in ('F','V','O'):
    assert v[k]['count']==sum(int(i['error']) for i in v[k]['items'])
    assert v[k]['denominator']==len(v[k]['items'])
   for k in ('H','N','E'):assert v[k]['count']==len(v[k]['findings'])
   assert v['R']['retained']+len(v['R']['missing_ids'])==v['R']['denominator']
   items[v['id']]=v
 assert set(items)==set(mapping)
 scores[who]=items;validation.append({'scorer':who,'outputs':len(items),'arithmetic_valid':True})
rows=[];disagreements=[]
for code,run in sorted(mapping.items(),key=lambda x:x[1]['packet_id']):
 a=scores['alpha'][code];b=scores['beta'][code];row={**run,'masked_id':code}
 for k in ('F','V','O','H','N','E'):
  row[k]=b[k]['count']
  if a[k]['count']!=b[k]['count']:disagreements.append({'packet_id':run['packet_id'],'id':code,'metric':k,'alpha':a[k]['count'],'beta':b[k]['count'],'adopted':b[k]['count']})
  if 'denominator' in b[k]:row[k+'_denominator_key']=b[k]['denominator']
 row['N_original_alpha']=a['N']['count'];row['N_original_beta']=b['N']['count']
 if run['packet_id'] in ('p10','p11','p12'):row['N']+=1
 row['R_retained']=b['R']['retained'];row['R_denominator']=b['R']['denominator']
 row['F_denominator_reclassified']=row['F_denominator_key']+(1 if run['case_id']=='case01' else 0)
 row['V_denominator_reclassified']=row['V_denominator_key']-(1 if run['case_id']=='case01' else 0)
 row['N_lenient_sensitivity']=0 if run['packet_id'] in ('p02','p08','p10','p11','p12') else row['N']
 raw=(R/by_packet[run['packet_id']]['frozen_path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==run['output_sha256']
 rows.append(row)
aggregates={}
for c in ('a','b','d'):
 rs=[v for v in rows if v['condition']==c]
 aggregates[c]={'runs':len(rs),**{k:sum(v[k] for v in rs) for k in ('F','V','O','H','N','E','R_retained','R_denominator','F_denominator_key','V_denominator_key','O_denominator_key','H_denominator_key','F_denominator_reclassified','V_denominator_reclassified','N_lenient_sensitivity')}}
# The preregistered rule requires primary improvements in both repeats in two cases.
paired=[];qualifying=[]
for case in ('case01','case02','case03','case04'):
 both=True
 for repeat in (1,2):
  b=next(x for x in rows if x['case_id']==case and x['repeat']==repeat and x['condition']=='b')
  d=next(x for x in rows if x['case_id']==case and x['repeat']==repeat and x['condition']=='d')
  no_worse=all(d[k]<=b[k] for k in ('F','V','O'))
  improved=any(d[k]<b[k] for k in ('F','V','O'))
  paired.append({'case':case,'repeat':repeat,'primary_no_worse':no_worse,'primary_improvement':improved})
  both=both and no_worse and improved
 if both:qualifying.append(case)
result={'adjudication_version':2,'post_audit_N_additions':[{'packet_id':x,'increment':1,'claim':'Unrecorded alternative-method agreement converted to no agreement','source':'case02 L38','audit':'report-audit/AUDIT.md'} for x in ('p10','p11','p12')],'basis':'Strict N adjudication starts from beta and adds the same unrecorded-to-not-done distinction for fallback agreement in p10/p11/p12; raw alpha and beta remain unchanged. F/V denominator reclassification is shown separately; numerators unchanged. E lacks uniform operationalization and is not used for effectiveness comparison.', 'validation':validation,'independent_disagreements':disagreements,'rows':rows,'condition_aggregates':aggregates,'paired_primary_comparison':paired,'fixtures_with_improvement_in_both_repeats':qualifying,'clear_advantage_d_over_b':False,'decision_reason':'No matched pair improved any F/V/O dimension, so the registered rule fails irrespective of N disputes or the F/V reclassification.'}
assert not qualifying and not any(x['primary_improvement'] for x in paired)
(R/'adjudicated-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
with (R/'results.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
print(json.dumps({'aggregates':aggregates,'disagreements':disagreements,'clear_advantage':False,'arithmetic':validation},ensure_ascii=False,indent=2))
