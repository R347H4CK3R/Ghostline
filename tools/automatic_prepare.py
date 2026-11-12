"""Source-bound anonymous F5 candidates. No character identity or RVC claim."""
import hashlib,json,math,os,pathlib,re,shutil,tempfile
from tools.video_request import validate
from tools.video_queue import video_id
from tools.video_reference import acquire,ffmpeg_path
from tools.video_prepare import ReviewRequired
from tools.voice_pack import _audio
from tools.process_control import checked_process
from tools.master_voices import _publish_lock


def prepare(request,specifications,*,analyze,transcribe,acquire_source=acquire,cancelled=lambda:False,activity=lambda *args:None,commit=None):
 request=validate(request);identifier=video_id(request['videoURL']);root=pathlib.Path(specifications)
 if cancelled():raise InterruptedError('Candidate preparation paused')
 if not callable(transcribe) or not callable(analyze):raise ReviewRequired('Local speaker analysis and transcription must be configured')
 if root.is_symlink():raise ValueError('Linked specifications are unsupported')
 root=root.resolve();root.mkdir(parents=True,exist_ok=True);output=root/(identifier+'.json')
 if output.exists() or output.is_symlink():raise FileExistsError('Prepared references already exist')
 movie=None;rows=[];files={};analysis=None;source_hash=None
 with _publish_lock(root/('.'+identifier+'.prepare.lock')):
  try:
   with acquire_source(request['videoURL'],[dict(id='candidate-probe',start=0,end=.5)],cancelled=cancelled,activity=activity) as source:
    if source['videoID']!=identifier:raise ValueError('Downloaded source identity changed')
    movie=pathlib.Path(source['privateMoviePath']);source_hash=source['sourceSHA256']
    if not isinstance(source_hash,str) or not re.fullmatch('[a-f0-9]{64}',source_hash):raise ValueError('Invalid source proof')
    with tempfile.TemporaryDirectory(prefix='.candidate-audio-',dir=root) as scratch:
     scratch=pathlib.Path(scratch);decoded=scratch/'analysis.wav';ff=ffmpeg_path()
     checked_process([ff,'-v','error','-threads','1','-i',str(movie),'-t','1800.02','-fs','57600800','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(decoded)],timeout=90,cancelled=cancelled)
     activity('speaker_analyzing');analysis=analyze(decoded,cancelled)
     if not isinstance(analysis,dict) or analysis.get('schemaVersion')!=1 or analysis.get('labelsVerified') is not False or analysis.get('speakerSeparated') is not False:raise ValueError('Invalid candidate-analysis evidence')
     candidates=analysis.get('candidates')
     if not isinstance(candidates,list) or len(candidates)>32:raise ValueError('Candidate count exceeds limit')
     seen=set();audio_hashes=set();omitted=[]
     for index,row in enumerate(candidates):
      if cancelled():raise InterruptedError('Candidate preparation paused')
      if not isinstance(row,dict) or type(row.get('group')) is not int or not 1<=row['group']<=32 or row['group'] in seen:raise ValueError('Invalid or repeated speaker group')
      seen.add(row['group'])
      start,end=row.get('start'),row.get('end')
      if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end)) or not 0<=start<end<=1800 or not 3<=end-start<=12.001:raise ValueError('Invalid candidate timing')
      # IDs are source-specific; no unknown voice may replace an existing named character.
      profile='video-'+hashlib.sha256(identifier.encode()).hexdigest()[:16]+'-speaker-'+str(row['group']).zfill(2)
      wav=scratch/(profile+'.wav');activity('extracting',index,len(candidates))
      checked_process([ff,'-v','error','-threads','1','-ss',str(start),'-i',str(movie),'-t',str(end-start),'-vn','-ac','1','-ar','24000','-c:a','pcm_s16le',str(wav)],timeout=30,cancelled=cancelled)
      data=wav.read_bytes();_audio(data);digest=hashlib.sha256(data).hexdigest()
      if digest in audio_hashes:omitted.append(dict(group=row['group'],reason='duplicate-reference'));continue
      activity('transcribing',index,len(candidates));text=transcribe(wav)
      if not isinstance(text,str) or len(text)>3000 or len(re.findall(r'\b\w+\b',text))<3 or re.search(r'^\s*[\[(](music|applause|laughter|silence)[\])]',text,re.I):
       omitted.append(dict(group=row['group'],reason='insufficient-transcribed-speech'));continue
      audio_hashes.add(digest);files[profile+'.wav']=data
      metadata=dict(id=profile,name='Speaker '+str(row['group']).zfill(2)+' (unreviewed)',categories=['Unreviewed speaker candidates'],source='Private video '+request['videoURL']+'; SHA-256 '+source_hash+'; segment '+str(start)+' to '+str(end)+' seconds; anonymous automatic speaker grouping, not verified character identity',permission=request['sourceUse']['record'],referenceText=text.strip())
      rows.append(dict(metadata=metadata,referenceSHA256=digest,referenceTranscriptStatus='automatic-needs-review',candidateEvidence=dict(group=row['group'],start=start,end=end,identityVerified=False,overlapExcluded=False)))
     if not rows:raise ReviewRequired('No usable speech candidates; review the source or provide clean references')
     provenance=dict(videoID=identifier,sourceURL=request['videoURL'],sourceSHA256=source_hash,requestID=request['requestID'],sourceUse=request['sourceUse'],identityVerified=False,likenessVerified=False,trainedRVC=False,analysisEngine=analysis.get('engine','unknown'),candidateLimit=32,analysisTruncated=analysis.get('truncated') is True,omitted=omitted)
     revision=hashlib.sha256(json.dumps(dict(profiles=rows,provenance=provenance),sort_keys=True).encode()).hexdigest()
     target=root/'references'/identifier/revision
     if any(p.is_symlink() for p in [target,*target.parents] if p!=root.parent):raise ValueError('Linked reference destinations are unsupported')
     target.parent.mkdir(parents=True,exist_ok=True)
     with tempfile.TemporaryDirectory(prefix='.candidate-reference-',dir=target.parent) as directory:
      stage=pathlib.Path(directory)
      for name,data in files.items():
       with (stage/name).open('wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
      if target.exists():
       if not target.is_dir() or set(p.name for p in target.iterdir())!=set(files) or any((target/name).is_symlink() or (target/name).read_bytes()!=data for name,data in files.items()):raise ValueError('Existing candidate revision conflicts')
      # Publish the entire immutable revision in one filesystem operation.
      # A failed copy must never leave a partial directory at the final name.
      else:stage.rename(target)
     for row in rows:row['referenceFile']=(target/(row['metadata']['id']+'.wav')).relative_to(root).as_posix()
     spec=dict(schemaVersion=1,videoURL=request['videoURL'],profiles=rows,provenance=provenance)
  finally:
   # Emitted only after the acquisition context actually removed the downloaded movie.
   if movie is not None and not movie.exists():activity('temporary_media_removed')
  if cancelled():raise InterruptedError('Candidate preparation paused before commit')
  fd,name=tempfile.mkstemp(prefix='.candidate-spec-',dir=root)
  try:
   with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(spec,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
   def publish_pointer():
    if output.exists() or output.is_symlink():raise FileExistsError('Existing prepared specification was preserved')
    os.replace(name,output)
   if commit is None:publish_pointer()
   else:commit(publish_pointer)
  finally:pathlib.Path(name).unlink(missing_ok=True)
  return output
