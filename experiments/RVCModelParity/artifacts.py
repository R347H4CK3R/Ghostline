import hashlib,pathlib,re,json,sys
LIMIT=512*1024*1024
def row(root,name):
 if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+',name) or name in ['.','..']:raise ValueError('Unsafe artifact name')
 p=pathlib.Path(root)/name
 if p.is_symlink() or not p.is_file() or not 0<p.stat().st_size<=LIMIT:raise ValueError('Invalid artifact')
 with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 return dict(name=name,bytes=p.stat().st_size,sha256=digest)
def manifest(root,names,source):
 if not re.fullmatch('[a-f0-9]{40}',source) or not 0<len(names)<=32 or len(names)!=len(set(names)):raise ValueError('Invalid source or file set')
 return dict(source=source,files=[row(root,n) for n in names])
def verify(root,m,source):
 if m.get('source')!=source:raise ValueError('Source mismatch')
 expected=manifest(root,[r['name'] for r in m['files']],source)
 if m!=expected:raise ValueError('Artifact bytes changed')
if __name__=='__main__':
 p=pathlib.Path(sys.argv[1]);verify(p,json.loads((p/'manifest.json').read_text()),sys.argv[2]);print('Exact-source artifact bytes verified')
