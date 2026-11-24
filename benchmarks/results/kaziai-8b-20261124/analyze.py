"""Analyze only recorded JSON; no inference/runtime code is imported."""
import json
import statistics
from pathlib import Path

root=Path(__file__).resolve().parent/'evidence'
arms=['native1','lattice_fifo1','lattice_preempt1','native2','lattice_preempt2']
rows=[]
for arm in arms:
    path=root/'results'/f'{arm}.json'
    if not path.exists():continue
    data=json.loads(path.read_text())
    traces=data.get('traces',[])
    row={'arm':arm,'slots':data['slots'],'arm_error':data.get('arm_error'),'trace_count':len(traces)}
    for language in ['en','sw']:
        good=[t for t in traces if t['language']==language and t['interactive'].get('status')=='completed']
        values=[t['interactive']['ttft_ms']/1000 for t in good if t['interactive'].get('ttft_ms') is not None]
        row[language+'_ttft_seconds']=statistics.median(values) if values else None
        row[language+'_ttft_range']=[min(values),max(values)] if values else None
        completions=[t['interactive']['total_ms']/1000 for t in good]
        row[language+'_completion_seconds']=statistics.median(completions) if completions else None
    bulk=[t['background']['total_ms']/1000 for t in traces if t['background'].get('status')=='completed']
    row['background_seconds']=statistics.median(bulk) if bulk else None
    row['background_range']=[min(bulk),max(bulk)] if bulk else None
    row['fact_pass_count']=sum(t.get('interactive_fact_pass',False) for t in traces)
    row['failed_trace_requests']=sum(t[role].get('status')!='completed' for t in traces for role in ['interactive','background'])
    cancel=data.get('cancellation',{})
    row['cancel_peer_preserved']=cancel.get('peer',{}).get('status')=='completed'
    row['cancel_recovery_pass']=cancel.get('recovery',{}).get('status')=='completed' and '4' in cancel.get('recovery',{}).get('text','')
    row['cancel_slots']=cancel.get('slots')
    row['tool_api_status']=data.get('tool_compatibility',{}).get('status')
    row['output_1024_status']=data.get('output_budget_compatibility',{}).get('status')
    row['receipt_json']=data.get('receipt_extraction',{}).get('parsed')
    saturated=data.get('saturated_two_bulk',{})
    row['saturated_ttft_seconds']=saturated.get('interactive',{}).get('ttft_ms',0)/1000 if saturated else None
    row['saturated_math_pass']='204' in saturated.get('interactive',{}).get('text','') if saturated else None
    fractions=[]
    for trace in traces:
        before=trace['hardware_before']['cpu_times'];after=trace['hardware_after']['cpu_times']
        total=sum(after)-sum(before);steal=after[7]-before[7]
        if total>0:fractions.append(steal/total)
    row['max_trace_cpu_steal_fraction']=max(fractions) if fractions else None
    row['observed_swap_kb']=max((t['hardware_after']['swap_total_kb']-t['hardware_after']['swap_free_kb'] for t in traces),default=None)
    rows.append(row)

comparisons=[]
baseline=json.loads((root/'results/native1.json').read_text()) if (root/'results/native1.json').exists() else None
if baseline:
    for arm in arms[1:]:
        path=root/'results'/f'{arm}.json'
        if not path.exists():continue
        data=json.loads(path.read_text())
        outcomes=[]
        for case in data.get('traces',[]):
            other=next((x for x in baseline['traces'] if x['repeat']==case['repeat'] and x['language']==case['language']),None)
            if other:outcomes.append({'repeat':case['repeat'],'language':case['language'],'background_exact_match':case['background'].get('text')==other['background'].get('text'),'interactive_exact_match':case['interactive'].get('text')==other['interactive'].get('text')})
        comparisons.append({'arm':arm,'outcomes':outcomes})

resources=root/'resource-samples.jsonl'
if resources.exists():
    samples=[json.loads(line) for line in resources.read_text().splitlines() if line.strip()]
    for row in rows:
        own=[s for s in samples if s['arm']==row['arm']]
        row['observed_worker_high_water_mib']=max((s['high_water_kb']/1024 for s in own),default=None)
        row['observed_worker_process_count']=len({s['pid'] for s in own})

summary={'scope':'Controlled 8B CPU pilot; medians over three repeats per language. No P95/P99 claim. Cold initial load excluded; preemption reload cost included.','arms':rows,'greedy_comparisons_to_native1':comparisons}
sampling=root/'results/sampling-comparison.json'
if sampling.exists():summary['sampling_comparisons']=json.loads(sampling.read_text())
(root/'summary.json').write_text(json.dumps(summary,indent=2))
for row in rows:print(json.dumps(row))
print(json.dumps({'comparisons':comparisons,'sampling':summary.get('sampling_comparisons')}))
