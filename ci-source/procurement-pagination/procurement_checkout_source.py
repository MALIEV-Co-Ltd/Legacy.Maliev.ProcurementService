"""Restore exact pinned Git bytes in four clean, owned hosted source checkouts."""
import hashlib,json,os,stat,sys,zipfile
from pathlib import Path
import procurement_consumer_association as association
from procurement_pagination_hosted_guards import require

def source_rows():
    path=Path(__file__).resolve().parent/'consumer-source-pins.json'
    raw=path.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==association.PINS_SHA,'Original469 source pin bytes differ')
    rows=json.loads(raw)
    require(len(rows)==4 and {row['repository']:row['commit'] for row in rows}==association.EXPECTED,'Original four immutable sources required')
    return rows

def restore(driver,base,dependencies):
    rows=source_rows();prepared=[]
    # Validate all four before changing a tracked source byte.
    for row in rows:
        name=row['repository'];root=Path(base) if name=='Legacy.Maliev.ProcurementService' else Path(dependencies)/name
        require(root.is_dir() and not root.is_symlink(),'Owned source root missing or aliased')
        _,head=driver.command('source-'+name+'-head',['git','rev-parse','HEAD'],root,10)
        require(head.strip()==row['commit'],'Original source HEAD differs')
        _,dirty=driver.command('source-'+name+'-clean',['git','status','--porcelain=v1','--untracked-files=all'],root,10)
        require(not dirty.strip(),'Source checkout has unrelated changes; preserve')
        expected={entry['path']:entry for entry in row['files']}
        actual=set()
        for directory,folders,files in os.walk(root):
            folders[:]=[name for name in folders if name not in ('.git','bin','obj')]
            require(not any((Path(directory)/name).is_symlink() for name in folders),'Aliased source directory')
            actual.update((Path(directory)/name).relative_to(root).as_posix() for name in files if name!='.git')
        require(actual==set(expected),'Unexpected checkout source inventory; preserve')
        for name in expected:
            relative=Path(name)
            require(not relative.is_absolute() and '..' not in relative.parts,'Unsafe pinned source path')
            target=root/relative
            require(target.is_file() and not target.is_symlink() and not any(parent.is_symlink() for parent in target.parents),'Source file missing or aliased')
        archive=driver.root/('raw-source-'+row['repository']+'.zip')
        require(not archive.exists(),'Fresh owned source archive required')
        info=root/'.git/info'
        require(info.is_dir() and not info.is_symlink() and not (root/'.git').is_symlink(),'Owned fresh Git metadata required')
        attributes=info/'attributes'
        require(not attributes.exists(),'Pre-existing local Git attributes must be preserved')
        handle=identity=None
        custody={'path':str(attributes),'created':False,'identityCaptured':False,'handleClosed':False,'fileAbsent':False,'failures':[]}
        driver.receipt.setdefault('temporaryGitAttributes',[]).append(custody)
        try:
            handle=attributes.open('xb');custody['created']=True
            identity=os.fstat(handle.fileno());custody.update(identityCaptured=True,device=identity.st_dev,inode=identity.st_ino)
            handle.write(b'* -text -eol -export-ignore -export-subst\n')
            handle.close()
            driver.command('source-'+row['repository']+'-archive',['git','archive','--worktree-attributes','--format=zip','--output='+str(archive),row['commit']],root,20)
        finally:
            primary=sys.exception()
            failures=[]
            if handle is not None and identity is None and not handle.closed:
                try:identity=os.fstat(handle.fileno());custody.update(identityCaptured=True,device=identity.st_dev,inode=identity.st_ino)
                except BaseException as exc:failures.append(type(exc).__name__)
            if handle is not None:
                try:
                    if not handle.closed:handle.close()
                    custody['handleClosed']=handle.closed
                except BaseException as exc:failures.append(type(exc).__name__)
            try:
                if custody['created']:
                    require(identity is not None,'Temporary attribute identity uncertain; preserve')
                    current=attributes.stat()
                    require((current.st_dev,current.st_ino)==(identity.st_dev,identity.st_ino),'Owned temporary attribute identity changed; preserve')
                    attributes.unlink();custody['fileAbsent']=not attributes.exists()
            except BaseException as exc:failures.append(type(exc).__name__)
            custody['failures']=failures
            try:driver.save()
            except BaseException as exc:failures.append(type(exc).__name__)
            if failures:
                if primary is None:raise RuntimeError('Owned temporary Git attribute cleanup incomplete; inspect source receipt')
                try:primary.add_note('Owned temporary attribute cleanup failed; retained receipt records uncertainty.')
                except BaseException:pass
        require(archive.is_file() and not archive.is_symlink() and archive.stat().st_size<=32*1024*1024,'Owned raw archive unavailable or exceeds original output quota')
        with zipfile.ZipFile(archive) as z:
            files=[info for info in z.infolist() if not info.is_dir()]
            require(len(files)==len(expected) and {info.filename for info in files}==set(expected),'Raw Git archive inventory differs')
            for info in files:
                entry=expected[info.filename]
                require(not stat.S_ISLNK(info.external_attr>>16) and info.file_size==entry['bytes'],'Raw Git source type or size differs')
                raw=z.read(info)
                require(hashlib.sha256(raw).hexdigest()==entry['sha256'] and hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==entry['gitBlobOid'],'Raw Git source blob differs')
        prepared.append((row,root,archive))
    changed=[]
    for row,root,archive in prepared:
        with zipfile.ZipFile(archive) as z:
            for entry in row['files']:
                target=root/entry['path'];raw=z.read(entry['path'])
                require(len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256'],'Raw source changed after validation; preserve')
                if target.read_bytes()!=raw:
                    target.write_bytes(raw);changed.append(row['repository']+'/'+entry['path'])
    context=association.verify_context(base,dependencies)
    proof={'sourceOnly':True,'nativeExecuted':False,'rawGitSourceFiles':sum(len(row['files']) for row in rows),'restoredCheckoutPaths':changed,'exactSourceAssociation':context}
    driver.receipt['sourceCheckoutRestoration']=proof;driver.save()
    return proof
