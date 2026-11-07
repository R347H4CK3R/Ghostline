"""Development-only source inspection. Never uploads models or executes checkpoints."""
import hashlib,json,pathlib,urllib.request,urllib.error,zipfile,tempfile
from urllib.parse import quote
candidates=[
 ('Rick Sanchez','Homiebear/RickSanchez_450e_14400s','RickSanchez_450e_14400s.zip'),
 ('Morty Smith','MrSpringtroll/morty','morty.zip'),
 ('Morty Smith (Virtual Rick-Ality listing)','brookieisthatyou/MY-RVC-V2-MODELS','MortySmith.zip')]
def fetch(url,limit=2_000_000):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceMatrix-source-audit/1.0'}),timeout=60) as response:
  raw=response.read(limit+1)
  if len(raw)>limit:raise ValueError('Source exceeds size limit')
  return raw
results=[]
for name,repo,filename in candidates:
 row=dict(target=name,franchise='Rick and Morty',genres=['Animation & Cartoons','Science Fiction & Superheroes'],repository=repo,requestedFile=filename,status='unapproved',includedInApp=False,authorizationEstablished=False,inferenceTested=False)
 try:
  metadata=json.loads(fetch('https://huggingface.co/api/models/'+repo))
  revision=metadata['sha'];row['revision']=revision
  row['declaredLicense']=metadata.get('cardData',{}).get('license')
  row['repositoryFiles']=[s['rfilename'] for s in metadata.get('siblings',[])]
  row['publishedDocuments']={}
  for path in row['repositoryFiles']:
   if path.lower().split('/')[-1] in ['readme.md','license','license.md','license.txt','notice']:
    try:
     doc=fetch('https://huggingface.co/'+repo+'/resolve/'+revision+'/'+quote(path,safe='/')).decode()
     row['publishedDocuments'][path]=dict(sha256=hashlib.sha256(doc.encode()).hexdigest(),text=doc[:12000])
    except Exception as exc:row['publishedDocuments'][path]=dict(error=str(exc))
  if filename not in row['repositoryFiles']:
   row['archiveStatus']='Listed filename not present'
  else:
   url='https://huggingface.co/'+repo+'/resolve/'+revision+'/'+quote(filename,safe='/')
   with tempfile.TemporaryDirectory() as temporary:
    target=pathlib.Path(temporary)/'candidate.zip';digest=hashlib.sha256();size=0
    with urllib.request.urlopen(url,timeout=120) as source,target.open('wb') as out:
     while block:=source.read(1024*1024):
      size+=len(block)
      if size>512*1024*1024:raise ValueError('Archive exceeds development limit')
      digest.update(block);out.write(block)
    with zipfile.ZipFile(target) as archive:
     entries=archive.infolist()
     row['archiveEntries']=[dict(path=e.filename,bytes=e.file_size) for e in entries]
     row['containsRVCCheckpoint']=any(e.filename.lower().endswith('.pth') for e in entries)
     row['containsRetrievalIndex']=any(e.filename.lower().endswith('.index') for e in entries)
     for e in entries:
      if e.file_size<=100000 and pathlib.PurePosixPath(e.filename).name.lower() in ['license','license.txt','license.md','readme.txt','readme.md']:
       row['publishedDocuments']['archive:'+e.filename]=dict(text=archive.read(e).decode(errors='replace'))
    row.update(archiveStatus='Downloaded and inspected without extracting or executing',archiveBytes=size,archiveSHA256=digest.hexdigest())
  row['blockingChecks']=['Recording provenance and voice/likeness authorization require review','Redistribution permission requires review','RVC checkpoint is not a Phonon or OpenVoice conditioning file','No native iOS inference or resemblance verification']
 except Exception as exc:
  row['retrievalError']=str(exc);row['archiveStatus']='Could not verify source'
 results.append(row)
out=pathlib.Path('research-results');out.mkdir(exist_ok=True)
(out/'rick-morty-source-audit.json').write_text(json.dumps(dict(scope='Research candidates only; no model approved, voice generated, or likeness verified.',candidates=results),indent=2)+'\n')
for row in results:print(row['target'],row.get('archiveStatus'),row.get('retrievalError',''),flush=True)
