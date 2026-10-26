"""Exact original caller/dependency source association, before any SDK work."""
import hashlib,json,os
from pathlib import Path
from procurement_pagination_hosted_guards import require,install_spec
BASE='1249989e04040bd1326842ebf2e1f438369cf8c9'
SHARED='e5732037fe94b7ed6e5be2cd4c23dbf6ef5e2617'
EXPECTED={'Legacy.Maliev.ProcurementService':BASE,'Legacy.Maliev.ServiceDefaults':'ecb05cbbd68717e415f69df2ac488c1d323b1da3','Legacy.Maliev.CompatibilityContracts':'78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7','Legacy.Maliev.Workflows':SHARED}
def verify_context(base,dependencies):
    pins=Path(__file__).resolve().parent/'consumer-source-pins.json'
    require(hashlib.sha256(pins.read_bytes()).hexdigest()==PINS_SHA,'Consumer source association drift')
    rows=json.loads(pins.read_bytes())
    require(len(rows)==4 and {r['repository']:r['commit'] for r in rows}==EXPECTED,'Exact four source associations required')
    checked=[]
    for row in rows:
        root=Path(base) if row['repository']=='Legacy.Maliev.ProcurementService' else Path(dependencies)/row['repository']
        require(root.is_dir() and not root.is_symlink(),'Source checkout missing or aliased')
        actual=set()
        for directory,folders,files in os.walk(root):
            folders[:]=[name for name in folders if name not in ('.git','bin','obj')]
            require(not any((Path(directory)/name).is_symlink() for name in folders),'Aliased source directory')
            actual.update((Path(directory)/name).relative_to(root).as_posix() for name in files if name!='.git')
        require(actual=={entry['path'] for entry in row['files']},'Unexpected/stale source inventory')
        for entry in row['files']:
            path=Path(entry['path']);require(not path.is_absolute() and '..' not in path.parts,'Unsafe source path')
            target=root/path
            require(target.is_file() and not target.is_symlink(),'Required source file missing/aliased')
            raw=target.read_bytes()
            require(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],'Stale caller or dependency source bytes')
            require(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==entry['gitBlobOid'],'Git source identity differs')
        checked.append({'repository':row['repository'],'commit':row['commit'],'files':len(row['files'])})
    spec=install_spec((Path(dependencies)/'Legacy.Maliev.Workflows/actions/dotnet-validate/action.yml').read_text(encoding='utf-8'))
    require(spec['env']['GOTOOLCHAIN']=='go1.26.9','Actual published source toolchain differs')
    return {'sourceOnly':True,'nativeExecuted':False,'associations':checked,'reviewedGoStepSha256':spec['stepSha256'],'qualifiedSharedSourceCommit':SHARED}

PINS_SHA='8685ac5b697fc7586e877b5a87494d2aafc57634fa6ae950701aab55907cba21'
