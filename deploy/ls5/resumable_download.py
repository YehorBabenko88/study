"""Pinned HTTPS downloads and bounded extraction; no activation or implicit trust."""
import hashlib,json,os,re,stat,time,urllib.parse,urllib.request,uuid,zipfile
from pathlib import Path,PurePosixPath
import portable_ops as ops

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):raise ValueError('Artifact redirects require an explicitly pinned allowlisted URL')
def validate_url(url,allowed_hosts):
    parts=urllib.parse.urlsplit(url)
    if parts.scheme!='https' or parts.hostname not in set(allowed_hosts) or parts.username or parts.password or parts.fragment or parts.port not in (None,443):raise ValueError('Unapproved HTTPS artifact URL')
    return parts

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Explicit per-artifact exact CDN hosts, bounded hops, no credential forwarding."""
    def __init__(self,allowed_hosts,max_hops=3):
        self.allowed_hosts=set(allowed_hosts);self.max_hops=max_hops
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        validate_url(newurl,self.allowed_hosts)
        hops=getattr(request,'_study_redirect_hops',0)+1
        if hops>self.max_hops:raise ValueError('Artifact redirect hop limit exceeded')
        safe={name:value for name,value in request.header_items() if name.lower() in ('range','if-range','accept-encoding')}
        redirected=urllib.request.Request(newurl,headers=safe,method='GET')
        redirected._study_redirect_hops=hops
        return redirected

_OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

def atomic_json(path,value):
    path=Path(path);temporary=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,sort_keys=True,separators=(',',':'));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists():temporary.unlink()

def _safe_ancestors(path):
    for ancestor in (path,*path.parents):
        if ancestor.exists() and ops.linked(ancestor):raise ValueError('Linked download/extraction ancestors forbidden')

def _quarantine(path):
    if path.exists():os.replace(path,path.with_name(path.name+'.quarantine.'+uuid.uuid4().hex))

def download(artifact,target,allowed_hosts,*,opener=None,timeout=30,chunk_size=1024*1024):
    """Resume only against the same strong ETag and exact pinned byte range."""
    url=artifact['url'];parts=validate_url(url,allowed_hosts)
    redirects=artifact.get('redirect_hosts',[])
    if not isinstance(redirects,list) or any(not isinstance(host,str) or host not in set(allowed_hosts) for host in redirects):raise ValueError('Redirect hosts require explicit manifest allowlisting')
    size=artifact.get('size');expected=artifact.get('sha256')
    if type(size) is not int or not 0<size<=100_000_000_000 or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):raise ValueError('Pinned positive size and SHA256 required')
    target=Path(target);_safe_ancestors(target);target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        if target.is_file() and target.stat().st_size==size and ops.digest(target)==expected:return target
        _quarantine(target)
    partial=target.with_name(target.name+'.part');metadata=target.with_name(target.name+'.part.json')
    _safe_ancestors(partial);_safe_ancestors(metadata)
    if partial.is_file() and partial.stat().st_size==size and ops.digest(partial)==expected:
        os.replace(partial,target)
        if metadata.exists():metadata.unlink()
        return target
    offset=0;etag=None
    if partial.exists() and metadata.exists():
        try:
            saved=json.loads(metadata.read_text(encoding='utf-8'))
            if all(saved.get(key)==artifact.get(key) for key in ('url','size','sha256')) and isinstance(saved.get('etag'),str) and re.fullmatch(r'"[^"\r\n]+"',saved['etag']):
                offset=partial.stat().st_size;etag=saved['etag']
        except (OSError,ValueError):pass
    if not 0<offset<size:offset=0;etag=None
    headers={'Accept-Encoding':'identity'}
    if offset:headers.update({'Range':f'bytes={offset}-','If-Range':etag})
    request=urllib.request.Request(url,headers=headers)
    network_opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),SafeRedirect({parts.hostname,*redirects})) if redirects else _OPENER
    open_request=opener or network_opener.open
    with open_request(request,timeout=timeout) as response:
        status=response.status;received_etag=response.headers.get('ETag')
        if response.headers.get('Content-Encoding','identity').lower()!='identity':raise ValueError('Encoded artifact response forbidden')
        if offset and status==206:
            content_range=response.headers.get('Content-Range','')
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',content_range)
            if received_etag!=etag or not match or tuple(map(int,match.groups()))!=(offset,size-1,size):
                _quarantine(partial);_quarantine(metadata);raise ValueError('Resume entity or Content-Range changed')
        elif status==200:
            offset=0
        else:raise ValueError('Unexpected artifact response status')
        length=response.headers.get('Content-Length')
        if length is None or not length.isdigit() or int(length)!=size-offset:raise ValueError('Pinned response length mismatch')
        atomic_json(metadata,dict(artifact,etag=received_etag))
        try:
            with partial.open('ab' if offset else 'wb') as stream:
                total=offset
                while True:
                    chunk=response.read(min(chunk_size,size-total+1))
                    if not chunk:break
                    total+=len(chunk)
                    if total>size:raise ValueError('Artifact exceeds pinned size')
                    stream.write(chunk);stream.flush();os.fsync(stream.fileno())
            if total!=size:raise OSError('Interrupted artifact transfer')
            if ops.digest(partial)!=expected:raise ValueError('Artifact SHA256 mismatch')
        except ValueError:
            _quarantine(partial);_quarantine(metadata);raise
    os.replace(partial,target)
    if metadata.exists():metadata.unlink()
    return target


def extract_zip(source,destination,*,archive_root=None,max_files=50000,max_total=8_000_000_000,max_file=2_000_000_000,max_ratio=200):
    """Validate the entire central directory before writing a single member."""
    destination=Path(destination);_safe_ancestors(destination)
    prefix=PurePosixPath(archive_root) if archive_root else None
    if prefix and (prefix.is_absolute() or '..' in prefix.parts):raise ValueError('Unsafe archive root')
    names=set();members=[];total=0
    with zipfile.ZipFile(source) as archive:
        if len(archive.infolist())>max_files:raise ValueError('Archive file count exceeds bound')
        for item in archive.infolist():
            name=item.filename;path=PurePosixPath(name)
            mode=(item.external_attr>>16)&0xffff
            if not name or '\\' in name or ':' in name or path.is_absolute() or '..' in path.parts or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR)) or item.flag_bits&1:raise ValueError('Unsafe archive member')
            if any(part.endswith((' ','.')) or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*('COM'+str(i) for i in range(1,10)),*('LPT'+str(i) for i in range(1,10))} for part in path.parts):raise ValueError('Unsafe Windows archive member')
            if prefix:
                try:path=path.relative_to(prefix)
                except ValueError:raise ValueError('Archive member outside reviewed root')
                if not path.parts:continue
            normalized=str(path).casefold()
            if normalized in names:raise ValueError('Duplicate archive member')
            names.add(normalized);total+=item.file_size
            if item.file_size>max_file or total>max_total or (item.file_size and item.file_size/max(1,item.compress_size)>max_ratio):raise ValueError('Archive expansion exceeds bound')
            members.append((item,path))
        destination.mkdir(parents=True,exist_ok=True)
        for item,path in members:
            target=destination/Path(*path.parts)
            if not ops.inside(target,destination):raise ValueError('Archive escape')
            _safe_ancestors(target)
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as original,target.open('xb') as copied:
                count=0
                while True:
                    chunk=original.read(1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>item.file_size:raise ValueError('Archive member size changed')
                    copied.write(chunk)
                if count!=item.file_size:raise ValueError('Truncated archive member')
    return destination
