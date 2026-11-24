"""Check caller seed/temperature behavior under real preemption."""
import asyncio
import json
from pathlib import Path
import httpx
from benchmark import config, launch, shutdown, consume, spec, OUT


async def main():
    results=[]
    for label,lattice,policy in [('sampling_native1',False,'priority_fifo'),('sampling_lattice_preempt1',True,'priority_preemptive')]:
        settings,entry=config(1,label)
        backend,runtime,server,task,base,headers,args=await launch(settings,entry,lattice,policy)
        try:
            async with httpx.AsyncClient(headers=headers,timeout=210.0,trust_env=False) as client:
                warm=await consume(client,base,spec('What is 2 + 2? Reply only with the integer.',8),lattice)
                if warm['status']!='completed':raise RuntimeError('Real inference unavailable')
                for seed in [7,42,99]:
                    payload=spec('Write a friendly invoice reminder draft for Acme Ltd. Invoice INV009 is KES 1500 for support, due 30 November 2026. It needs an independent administrator approval before sending. Do not claim that a message was sent.',64,0,0.2)
                    payload['seed']=seed
                    arrived=asyncio.Event()
                    background=asyncio.create_task(consume(client,base,payload,lattice,signal=arrived))
                    await asyncio.wait_for(arrived.wait(),150)
                    foreground=await consume(client,base,spec('What is 17 times 12? Reply only with the integer.',8,3),lattice)
                    bg=await background
                    row={'arm':label,'temperature':0.2,'seed':seed,'background':bg,'interactive':foreground}
                    results.append(row)
                    (OUT/'sampling.json').write_text(json.dumps(results,indent=2))
                    print(json.dumps({'arm':label,'seed':seed,'background_status':bg['status'],'interactive_ms':round(foreground['total_ms'],1)}),flush=True)
                typed=await consume(client,base,spec('Extract this receipt into JSON only, no Markdown. vendor must be a string; date must be an ISO date string; total and tax must be JSON numbers without currency symbols; currency must be a string. Receipt: Nairobi Supplies, 2026-11-22, total KES 1160 including tax KES 160. Return exactly the keys vendor, date, total, tax, currency.',128,3),lattice)
                try:
                    typed['parsed']=json.loads(typed.get('text','').strip())
                    typed['exact_fields_pass']=typed['parsed']=={'vendor':'Nairobi Supplies','date':'2026-11-22','total':1160,'tax':160,'currency':'KES'}
                except ValueError:typed['exact_fields_pass']=False
                (OUT/(label+'-typed-receipt.json')).write_text(json.dumps(typed,indent=2))
        finally:await shutdown(backend,server,task)
    comparison=[]
    for seed in [7,42,99]:
        a=next(r for r in results if r['arm']=='sampling_native1' and r['seed']==seed)
        b=next(r for r in results if r['arm']=='sampling_lattice_preempt1' and r['seed']==seed)
        comparison.append({'seed':seed,'exact_output_match':a['background'].get('text')==b['background'].get('text'),'statuses':[a['background']['status'],b['background']['status']]})
    (OUT/'sampling-comparison.json').write_text(json.dumps(comparison,indent=2))
    print(json.dumps({'sampling_comparison':comparison}),flush=True)


if __name__=='__main__':asyncio.run(main())
