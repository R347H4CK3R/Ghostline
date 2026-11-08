"""Prepare reviewed video references for the queue processor."""
import hashlib,json,os,pathlib,re,shutil,tempfile
from tools.video_reference import acquire,validate_request
from tools.video_queue import video_id
from tools.voice_pack import _metadata,_audio
from tools.master_voices import _publish_lock

class ReviewRequired(ValueError):pass

def validate_recipe(recipe,*,transcribe_available=False):
 if not isinstance(recipe,dict) or recipe.get('schemaVersion')!=1:raise ValueError('Invalid video preparation recipe')
 if not isinstance(recipe.get('videoURL'),str):raise ValueError('Video URL must be text')
 binding=['inspectionRevision','inspectedSourceSHA256']
 if any(k in recipe for k in binding) and any(not isinstance(recipe.get(k),str) or not re.fullmatch(r'[a-f0-9]{64}',recipe[k]) for k in binding):raise ValueError('Invalid inspected source binding')
 identifier=video_id(recipe.get('videoURL',''));review=recipe.get('referenceUseReview',{})
 if not isinstance(review,dict) or review.get('decision')!='approved-local-processing' or any(not isinstance(review.get(k),str) or not review[k].strip() for k in ['reviewer','record']):raise ReviewRequired('Reference-use review and provenance record are required before downloading')
 segments=recipe.get('segments')
 if not isinstance(segments,list) or not 1<=len(segments)<=64:raise ValueError('Choose 1–64 reviewed reference segments')
 metadata={}
 for row in segments:
  if not isinstance(row,dict):raise ValueError('Invalid reference segment')
  if row.get('labelStatus') not in ['on-screen-label-reviewed','speaker-label-reviewed','original-speaker-reviewed']:raise ReviewRequired('Uncertain character or speaker labels need review before processing')
  if any(isinstance(row.get(k),bool) for k in ['start','end']):raise ValueError('Reference times must be numbers')
  m={k:row.get(k) for k in ['id','name','categories','source','permission']};text=row.get('referenceText','')
  if not isinstance(text,str):raise ValueError('Reference words must be text')
  if not text.strip() and not transcribe_available:raise ReviewRequired('Reference words or a local transcription engine are required')
  m['referenceText']=text.strip() or 'Pending local transcription';_metadata(m)
  if len(m['categories'])>50 or len(json.dumps(m).encode())>48000:raise ValueError('Reference metadata is too large')
  metadata[m['id']]=m
 validate_request(recipe['videoURL'],segments)
 return identifier,metadata

def prepare(recipe_path,spec_directory,*,cancelled=lambda:False,transcribe=None,downloader_factory=None,commit=None):
 recipe_path=pathlib.Path(recipe_path)
 if recipe_path.is_symlink() or not recipe_path.is_file() or recipe_path.stat().st_size>512000:raise ValueError('Invalid video preparation recipe')
 raw=recipe_path.read_bytes();recipe=json.loads(raw)
 identifier,metadata=validate_recipe(recipe,transcribe_available=transcribe is not None)
 segments=recipe['segments'];review=recipe['referenceUseReview']
 root=pathlib.Path(spec_directory)
 if root.is_symlink():raise ValueError('Choose a real specifications folder')
 root=root.resolve();root.mkdir(parents=True,exist_ok=True)
 with _publish_lock(root/('.'+identifier+'.prepare.lock')):
  if cancelled():raise InterruptedError('Video preparation paused')
  with acquire(recipe['videoURL'],segments,downloader_factory,cancelled=cancelled,max_duration=recipe.get('maxVideoSeconds',1800),max_bytes=recipe.get('maxDownloadBytes',268435456),max_download_seconds=recipe.get('maxDownloadSeconds',300)) as source:
   if source['videoID']!=identifier:raise ValueError('Downloaded video does not match the queued video ID')
   if 'inspectedSourceSHA256' in recipe and source['sourceSHA256']!=recipe['inspectedSourceSHA256']:raise ReviewRequired('Source bytes changed after inspection; new source review is required')
   rows=[];files={};owners=set()
   for segment in source['segments']:
    if cancelled():raise InterruptedError('Video preparation paused')
    data=pathlib.Path(segment['audioPath']).read_bytes();_audio(data);checksum=hashlib.sha256(data).hexdigest()
    if checksum!=segment['sha256'] or checksum in owners:raise ValueError('Prepared reference changed or repeats another segment')
    owners.add(checksum);m=dict(metadata[segment['id']]);provided=segment.get('referenceText','').strip()
    text=provided or transcribe(pathlib.Path(segment['audioPath']))
    if not isinstance(text,str) or not text.strip() or len(text)>3000:raise ReviewRequired('Reference transcription needs review')
    m['referenceText']=text.strip();m['source']+='; '+recipe['videoURL']+'; segment '+str(segment['start'])+'–'+str(segment['end'])+' seconds; video SHA-256 '+source['sourceSHA256']
    _metadata(m);files[m['id']+'.wav']=data
    rows.append(dict(metadata=m,referenceSHA256=checksum,referenceTranscriptStatus='provided' if provided else 'automatic-needs-review'))
   provenance=dict(videoID=identifier,sourceURL=recipe['videoURL'],sourceSHA256=source['sourceSHA256'],recipeSHA256=hashlib.sha256(raw).hexdigest(),referenceUseReview=review,labels='Reviewed source labels; no biometric identification',likenessVerified=False,authorizedLikeness=False)
   revision=hashlib.sha256(json.dumps(dict(profiles=rows,provenance=provenance),sort_keys=True).encode()).hexdigest()
   target=root/'references'/identifier/revision
   if any(p.is_symlink() for p in [target,*target.parents] if p!=root.parent):raise ValueError('Linked reference destinations are unsupported')
   target.parent.mkdir(parents=True,exist_ok=True)
   stage=pathlib.Path(tempfile.mkdtemp(prefix='.preparing-',dir=target.parent))
   try:
    for name,data in files.items():
     with (stage/name).open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    if target.exists():
     if not target.is_dir() or set(p.name for p in target.iterdir())!=set(files) or any((target/k).is_symlink() or (target/k).read_bytes()!=v for k,v in files.items()):raise ValueError('Existing prepared reference revision conflicts')
    else:os.rename(stage,target)
    for row in rows:row['referenceFile']=(target/(row['metadata']['id']+'.wav')).relative_to(root).as_posix()
    if cancelled():raise InterruptedError('Video preparation paused')
    if recipe_path.read_bytes()!=raw:raise ValueError('Recipe changed during preparation; retry with the new revision')
    spec=dict(schemaVersion=1,videoURL=recipe['videoURL'],profiles=rows,provenance=provenance)
    output=root/(identifier+'.json')
    if output.is_symlink():raise ValueError('Linked specifications are unsupported')
    fd,name=tempfile.mkstemp(prefix='.specification-',dir=root)
    try:
     with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(spec,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
     operation=lambda:os.replace(name,output)
     if commit is None:operation()
     else:commit(operation)
    finally:pathlib.Path(name).unlink(missing_ok=True)
    return output
   finally:
    if stage.exists():shutil.rmtree(stage)
