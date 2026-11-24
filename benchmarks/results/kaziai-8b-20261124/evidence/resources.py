import argparse
import json
import time
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=1200);args=parser.parse_args()
start=time.monotonic();root=Path('/home/boxd/trial');out=root/'resource-samples.jsonl'
with out.open('w') as sink:
    while time.monotonic()-start<args.seconds:
        log=(root/'benchmark.log').read_text() if (root/'benchmark.log').exists() else ''
        starts=[line for line in log.splitlines() if '"starting"' in line]
        arm=json.loads(starts[-1])['starting'] if starts else None
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                command=(proc/'cmdline').read_bytes()
                if not command.startswith(b'/home/boxd/trial/bin/llama-server\0'):continue
                status={line.split(':')[0]:line.split(':')[1].strip() for line in (proc/'status').read_text().splitlines() if ':' in line}
                sink.write(json.dumps({'time':time.time(),'arm':arm,'pid':int(proc.name),'rss_kb':int(status['VmRSS'].split()[0]),'high_water_kb':int(status['VmHWM'].split()[0])})+'\n');sink.flush()
            except (OSError,KeyError,ValueError):pass
        time.sleep(.25)
