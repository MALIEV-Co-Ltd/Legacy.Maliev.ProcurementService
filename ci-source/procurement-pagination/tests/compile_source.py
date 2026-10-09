"""Compile/check the source carrier without SDK or provider execution."""
import ast,hashlib,json
from pathlib import Path
import yaml
L=Path(__file__).resolve().parents[1];R=L.parents[1]
for row in json.loads((L/'reviewed-runtime-pins.json').read_bytes()):
    f=L/row['path']
    if f.stat().st_size!=row['bytes'] or hashlib.sha256(f.read_bytes()).hexdigest()!=row['sha256']:
        raise ValueError('Independently reviewed runtime source drift: '+row['path'])
files=list(L.rglob('*.py'))
for f in files:
    text=f.read_text(encoding='utf-8');compile(text,str(f),'exec')
    if any(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(text))):raise ValueError('Assert-dependent guard')
workflow=R/'.github/workflows/procurement-pagination-source-qualification.yml'
caller=yaml.safe_load(workflow.read_bytes());job=caller['jobs']['validate']
guard="${{ github.event_name == 'workflow_dispatch' && inputs.original_allocation_sha256 != '' && inputs.original_allocation_json != '' }}"
if job['if']!=guard or job['timeout-minutes']!=60:raise ValueError('Original dispatch admission or caps changed')
for step in job['steps']:
    lines=step.get('run','').splitlines()
    for i,line in enumerate(lines):
        if "<<'PY'" in line:
            end=lines.index('PY',i+1);compile('\n'.join(lines[i+1:end]),step['name'],'exec')
print(str(len(files))+' Python sources and caller snippets compile; reviewed V4 bytes retained; proposed dispatch-only route requires exact admission.')
