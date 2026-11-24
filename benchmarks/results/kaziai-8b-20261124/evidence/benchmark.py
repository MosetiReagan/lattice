"""Real Qwen3-8B pilot. Run only in the isolated trial VM; never simulates inference."""
import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import platform
import random
import socket
import time
from pathlib import Path

import httpx
import uvicorn
from lattice.api import create_app
from lattice.backends.llama_cpp import LlamaCppBackend
from lattice.backends.batched import BatchedLlamaBackend
from lattice.config import ModelEntry, Settings, file_hash
from lattice.runtime import Runtime
from lattice.types import GenerationRequest

ROOT = Path('/home/boxd/trial')
OUT = ROOT / 'results'
EXPECTED_MODEL_SHA = 'd98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785'
COMMON_FLAGS = ['--reasoning','off','--chat-template-kwargs','{"enable_thinking":false}',
    '--cache-type-k','q8_0','--cache-type-v','q8_0','--no-repack','--load-mode','mmap','--flash-attn','on','--jinja']


class KaziSingle(LlamaCppBackend):
    def extra_server_arguments(self):
        return super().extra_server_arguments() + COMMON_FLAGS


class KaziBatched(BatchedLlamaBackend):
    def extra_server_arguments(self):
        return super().extra_server_arguments() + COMMON_FLAGS


def config(slots, label):
    source = json.loads((ROOT/'source.json').read_text())
    model = ModelEntry(id='Qwen3-8B',path=str(ROOT/source['file']),sha256=source['sha256'],
        source_repository=source['repository'],source_revision=source['revision'],license=source['license'],
        precision='GGUF Q4_K_M',kv_bytes_per_token=147456)
    files = {str(p):file_hash(p) for p in (ROOT/'bin').glob('*.so*') if p.is_file()}
    settings = Settings(backend_binary=str(ROOT/'bin/llama-server'),backend_sha256=file_hash(ROOT/'bin/llama-server'),
        backend_commit='54cde7106a6b4013a053f13bb4a5d91683e7338d',backend_files=files,models=[model],
        context_tokens=8192,threads=4,batch_tokens=512,ubatch_tokens=128,native_slots=slots,
        worker_address_space_mb=16384,host_reserve_mb=4096,startup_timeout_seconds=120.0,
        max_queue=16,requests_per_minute=10000,native_ram_prompt_archive=False,log_directory=str(OUT/label))
    return settings, model


def hardware():
    cpu = Path('/proc/stat').read_text().splitlines()[0].split()[1:9]
    mem = {line.split(':')[0]:int(line.split(':')[1].split()[0]) for line in Path('/proc/meminfo').read_text().splitlines() if line.split(':')[1].split()[0].isdigit()}
    return {'cpu_times':[int(x) for x in cpu], 'available_memory_kb':mem['MemAvailable'],
        'swap_free_kb':mem['SwapFree'], 'swap_total_kb':mem['SwapTotal']}


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); return sock.getsockname()[1]


def spec(text, cap, priority=0, temperature=0.0):
    return {'model':'Qwen3-8B','messages':[{'role':'system','content':'You are KaziAI. Use only supplied facts. Follow the requested language. Do not show reasoning.'},
        {'role':'user','content':text}], 'max_tokens':cap,'temperature':temperature,'seed':42,
        'priority':priority,'timeout_seconds':180.0,'stream':True}


async def prepare_native(client, base, payload):
    response = await client.post(base+'/apply-template',json={'messages':payload['messages']})
    response.raise_for_status()
    encoded = await client.post(base+'/tokenize',json={'content':response.json()['prompt'],'add_special':True,'parse_special':True})
    encoded.raise_for_status()
    return {'prompt':encoded.json()['tokens'],'n_predict':payload['max_tokens'],'stream':True,
        'temperature':payload['temperature'],'seed':payload['seed'],'top_k':0,'top_p':1.0,'min_p':0.0,
        'repeat_penalty':1.0,'presence_penalty':0.0,'frequency_penalty':0.0,
        'samplers':['temperature'],'cache_prompt':False,'return_tokens':True}


async def consume(client, base, payload, lattice, signal=None, cancel_after=None):
    start=time.perf_counter(); first=None; pieces=[]; count=0; metadata={}; done=False
    try:
        body=payload if lattice else await prepare_native(client,base,payload)
        async with client.stream('POST',base+('/v1/chat/completions' if lattice else '/completion'),json=body) as response:
            if response.status_code != 200:
                raw=await response.aread()
                return {'status':'http_error','http_status':response.status_code,'error':raw.decode()[:1000], 'total_ms':(time.perf_counter()-start)*1000}
            async for line in response.aiter_lines():
                if not line.startswith('data: '):continue
                if line[6:]=='[DONE]':done=True;break
                event=json.loads(line[6:])
                if 'error' in event:
                    return {'status':'stream_error','error':event['error'],'text':''.join(pieces),'total_ms':(time.perf_counter()-start)*1000}
                if lattice:
                    choice=(event.get('choices') or [{}])[0]
                    text=choice.get('delta',{}).get('content','')
                    metadata=event.get('lattice',metadata)
                    if event.get('usage'): count=event['usage'].get('completion_tokens',count)
                else:
                    text=event.get('content','')
                    count+=len(event.get('tokens',[]))
                    if event.get('stop'):
                        done=True;metadata=event
                        count=event.get('tokens_predicted',count)
                if text:
                    if first is None:first=time.perf_counter()
                    pieces.append(text)
                    if signal and len(pieces)>=3:signal.set()
                    if cancel_after and len(pieces)>=cancel_after:
                        return {'status':'client_cancelled','text':''.join(pieces),'total_ms':(time.perf_counter()-start)*1000,'ttft_ms':(first-start)*1000}
        text=''.join(pieces)
        return {'status':'completed' if done else 'incomplete','text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'ttft_ms':None if first is None else (first-start)*1000,'total_ms':(time.perf_counter()-start)*1000,
            'completion_tokens':count,'metadata':metadata}
    except Exception as error:
        return {'status':'exception','error':type(error).__name__+': '+str(error),'text':''.join(pieces), 'total_ms':(time.perf_counter()-start)*1000}
    finally:
        if signal:signal.set()


async def launch(settings, entry, lattice, policy):
    settings.admission_policy=policy
    backend=(KaziSingle if settings.native_slots==1 else KaziBatched)(settings,entry)
    await backend.configure(GenerationRequest.model_validate(spec('Reply with the number 4.',8)))
    await backend.start()
    assert backend.process and backend.process.poll() is None
    assert backend.identity['model_sha256']==EXPECTED_MODEL_SHA
    runtime=None;server=None;task=None;api_key=None
    if lattice:
        runtime=Runtime(settings,entry.id,backend)
        api_key='isolated-trial-'+os.urandom(24).hex()
        listen=port(); server=uvicorn.Server(uvicorn.Config(create_app(settings,runtime,api_key,preload=False),host='127.0.0.1',port=listen,log_level='warning',access_log=False))
        task=asyncio.create_task(server.serve())
        for _ in range(100):
            if server.started:break
            if task.done():await task
            await asyncio.sleep(.05)
        if not server.started:raise RuntimeError('Real Lattice HTTP server did not start')
        base=f'http://127.0.0.1:{listen}';headers={'Authorization':'Bearer '+api_key}
    else:base=backend.base_url;headers=backend.headers
    args=list(backend.process.args)
    for i,value in enumerate(args):
        if value=='--api-key' and i+1<len(args):args[i+1]='REDACTED'
    return backend,runtime,server,task,base,headers,args


async def shutdown(backend,server,task):
    if server:
        server.should_exit=True
        try:await asyncio.wait_for(task,15)
        except TimeoutError:task.cancel();await asyncio.gather(task,return_exceptions=True)
    if backend:
        closer=getattr(backend,'aclose',None)
        if closer:await closer()
        else:backend.stop()


async def run_arm(label,lattice,slots,policy,repeats):
    settings,entry=config(slots,label)
    backend=None;server=None;task=None
    result={'arm':label,'lattice':lattice,'slots':slots,'policy':policy,'traces':[], 'hardware_before':hardware()}
    try:
        backend,runtime,server,task,base,headers,args=await launch(settings,entry,lattice,policy)
        result['worker_arguments']=args;result['backend_identity']=backend.identity
        result['startup_ms']=backend.worker_startup_ms
        async with httpx.AsyncClient(headers=headers,timeout=httpx.Timeout(210.0,connect=10.0),trust_env=False) as client:
            warm=await consume(client,base,spec('What is 2 + 2? Reply only with the integer.',8,3),lattice)
            result['warmup']=warm
            if warm['status']!='completed' or '4' not in warm['text']:raise RuntimeError('Real model warmup failed: '+str(warm))
            for repeat in range(repeats):
                for language in ['en','sw']:
                    context='Customer Acme Ltd in Nairobi. Invoice INV009 is KES 1500 for support, due 30 November 2026. Budget KES 2000; expenses KES 2300. All invoice and expense actions require an independent administrator. '
                    bulk=spec('Summarize these business facts in six numbered points, including amounts, dates and approval requirements. '+context*4,96,0)
                    quick=spec('What is 17 times 12? Reply only with the integer.' if language=='en' else 'Jibu kwa Kiswahili kwa sentensi moja: Acme Ltd inadaiwa KES 1500 kwa huduma za msaada. Usibadilishe kiasi.',8 if language=='en' else 64,3)
                    arrived=asyncio.Event(); before=hardware()
                    background=asyncio.create_task(consume(client,base,bulk,lattice,signal=arrived))
                    await asyncio.wait_for(arrived.wait(),150)
                    foreground=await consume(client,base,quick,lattice)
                    bg=await background
                    trace={'repeat':repeat,'language':language,'background':bg,'interactive':foreground,'hardware_before':before,'hardware_after':hardware()}
                    trace['interactive_fact_pass']=foreground.get('status')=='completed' and ('204' in foreground.get('text','') if language=='en' else 'Acme' in foreground.get('text','') and ('1500' in foreground.get('text','').replace(',','').replace(' ','')))
                    result['traces'].append(trace)
                    OUT.mkdir(exist_ok=True);(OUT/(label+'.json')).write_text(json.dumps(result,indent=2))
                    print(json.dumps({'arm':label,'repeat':repeat,'language':language,'interactive_ms':round(foreground['total_ms'],1),'ttft_ms':foreground.get('ttft_ms'),'background_ms':round(bg['total_ms'],1),'statuses':[bg['status'],foreground['status']],'fact_pass':trace['interactive_fact_pass']}),flush=True)
            if slots > 1:
                signals=[asyncio.Event(),asyncio.Event()]
                saturated=[asyncio.create_task(consume(client,base,spec('Summarize these business facts in six numbered points. '+context*4,96,0),lattice,signal=signal)) for signal in signals]
                await asyncio.wait_for(asyncio.gather(*(signal.wait() for signal in signals)),150)
                quick=await consume(client,base,spec('What is 17 times 12? Reply only with the integer.',8,3),lattice)
                bulk=await asyncio.gather(*saturated)
                result['saturated_two_bulk']={'interactive':quick,'backgrounds':bulk,'runtime_counters':runtime.metrics()['counters'] if runtime else None}
            # A client-disconnected stream must not poison a simultaneous peer or later request.
            begun=asyncio.Event()
            peer=asyncio.create_task(consume(client,base,spec('List five invoice review checks. Do not show reasoning.',64,0),lattice,signal=begun))
            await asyncio.wait_for(begun.wait(),150)
            cancelled=await consume(client,base,spec('Count from one onwards, one number per line.',128,3),lattice,cancel_after=2)
            peer_result=await peer
            await asyncio.sleep(.5)
            recovery=await consume(client,base,spec('What is 2 + 2? Reply only with the integer.',8,3),lattice)
            result['cancellation']={'cancelled':cancelled,'peer':peer_result,'recovery':recovery,'slots':getattr(backend,'slot_stats',lambda:None)(), 'runtime':runtime.metrics()['counters'] if runtime else None}
            extraction=await consume(client,base,spec('Extract this receipt and return only JSON, with exactly these keys: vendor, date, total, tax, currency. Receipt: Nairobi Supplies; date 2026-11-22; total KES 1160 including tax KES 160.',128,3),lattice)
            try:
                parsed=json.loads(extraction.get('text','').strip())
                extraction['parsed']=parsed
                extraction['exact_fields_pass']=parsed=={'vendor':'Nairobi Supplies','date':'2026-11-22','total':1160,'tax':160,'currency':'KES'}
            except ValueError:extraction['exact_fields_pass']=False
            result['receipt_extraction']=extraction
            # Native tool-call production compatibility vs Lattice's public schema.
            tools=[{'type':'function','function':{'name':'search_customers','description':'Search a customer by name','parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query'],'additionalProperties':False}}}]
            tool_body={'model':'Qwen3-8B','messages':[{'role':'user','content':'Find the customer Acme Ltd. Call search_customers.'}],'tools':tools,'tool_choice':{'type':'function','function':{'name':'search_customers'}},'max_tokens':128,'temperature':0.0,'stream':False}
            tool_reply=await client.post(base+'/v1/chat/completions',json=tool_body)
            result['tool_compatibility']={'status':tool_reply.status_code,'response':tool_reply.json()}
            if lattice:
                budget_reply=await client.post(base+'/v1/chat/completions',json={'model':'Qwen3-8B','messages':[{'role':'user','content':'Hello'}],'max_tokens':1024})
                result['output_budget_compatibility']={'status':budget_reply.status_code,'response':budget_reply.json()}
        result['hardware_after']=hardware()
    except Exception as error:
        result['arm_error']=type(error).__name__+': '+str(error)
        print(json.dumps({'arm':label,'arm_error':result['arm_error']}),flush=True)
    finally:
        await shutdown(backend,server,task)
        OUT.mkdir(exist_ok=True);(OUT/(label+'.json')).write_text(json.dumps(result,indent=2))
    return result


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--repeats',type=int,default=3);parser.add_argument('--arms',nargs='*')
    args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    if file_hash(ROOT/'Qwen3-8B-Q4_K_M.gguf')!=EXPECTED_MODEL_SHA:raise RuntimeError('Pinned model hash mismatch')
    manifest={'source_commit':'4fd5276480b4730240d3011bceac02e69839d1e8','native_commit':'54cde7106a6b4013a053f13bb4a5d91683e7338d','model_sha256':EXPECTED_MODEL_SHA,
        'machine':platform.platform(),'cpu':Path('/proc/cpuinfo').read_text().split('model name')[1].splitlines()[0].strip(),
        'common_flags':COMMON_FLAGS,'threads':4,'context_per_slot':8192,'background_cap':96,'repeats_per_language':args.repeats,
        'adaptations':'Only native launch flags matched to KaziAI; scheduler cancellation fix recorded separately. No simulation fallback.', 'hardware':hardware()}
    manifest['scheduler_patch_sha256']=file_hash(ROOT/'scheduler.patch') if (ROOT/'scheduler.patch').exists() else None
    manifest['native_library_search_path']=os.environ.get('LD_LIBRARY_PATH')
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    arms=[('native1',False,1,'priority_fifo'),('lattice_fifo1',True,1,'priority_fifo'),('lattice_preempt1',True,1,'priority_preemptive'),('native2',False,2,'priority_fifo'),('lattice_preempt2',True,2,'priority_preemptive')]
    if args.arms:arms=[arm for arm in arms if arm[0] in args.arms]
    for arm in arms:
        print(json.dumps({'starting':arm[0]}),flush=True)
        await run_arm(*arm,repeats=args.repeats)


if __name__=='__main__':asyncio.run(main())
