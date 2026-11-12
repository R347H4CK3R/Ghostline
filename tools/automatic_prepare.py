"""Source-bound anonymous F5 candidates. No character identity or RVC claim."""
import hashlib,json,math,os,pathlib,re,shutil,tempfile,wave
from tools.video_request import validate
from tools.video_queue import video_id
from tools.video_reference import acquire,ffmpeg_path
from tools.video_prepare import ReviewRequired
from tools.voice_pack import _audio
from tools.process_control import checked_process
from tools.master_voices import _publish_lock


def _canonical(value):
 return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8')

def analysis_evidence(analysis,source_sha,identifier,source_duration,decoded_duration):
 """Bounded projection only: timestamps are tentative, not clean/isolated speech."""
 def number(value):return type(value) in (int,float) and math.isfinite(value)
 if not isinstance(source_sha,str) or not re.fullmatch('[a-f0-9]{64}',source_sha) or not re.fullmatch('[A-Za-z0-9_-]{11}',identifier):raise ValueError('Invalid evidence source binding')
 if not number(decoded_duration) or not 0<decoded_duration<=1800.02:raise ValueError('Invalid measured PCM duration')
 if source_duration is not None and (not number(source_duration) or not 0<source_duration<=1800 or abs(decoded_duration-source_duration)>1):raise ValueError('Declared duration disagrees with measured PCM')
 if not isinstance(analysis,dict) or type(analysis.get('schemaVersion')) is not int or analysis['schemaVersion']!=1 or analysis.get('engine')!='speechbrain-ecapa-silero' or analysis.get('labelsVerified') is not False or analysis.get('speakerSeparated') is not False:raise ValueError('Unsupported analysis evidence')
 duration=analysis.get('durationSeconds')
 if duration is not None and (not number(duration) or abs(duration-decoded_duration)>.05):raise ValueError('Analysis duration does not match decoded source')
 for flag in ('truncated','groupLimitExceeded'):
  if flag in analysis and type(analysis[flag]) is not bool:raise ValueError('Invalid analysis flag')
 bound=decoded_duration
 def interval(row):
  if not isinstance(row,dict) or type(row.get('group')) is not int or not 1<=row['group']<=32:raise ValueError('Invalid tentative group')
  start,end=row.get('start'),row.get('end')
  if any(not number(v) for v in (start,end)) or not 0<=start<end<=bound+.000001 or not 3<=end-start<=12.001:raise ValueError('Invalid source-bound interval')
  return dict(group=row['group'],start=start,end=end)
 candidates=analysis.get('candidates')
 if not isinstance(candidates,list) or len(candidates)>32:raise ValueError('Candidate count exceeds bound')
 chosen=[interval(row) for row in candidates];groups={row['group'] for row in chosen}
 if len(groups)!=len(chosen):raise ValueError('Repeated candidate group')
 raw=analysis.get('memberIntervals',[])
 if not isinstance(raw,list) or len(raw)>512:raise ValueError('Alternate interval count exceeds bound')
 members=[interval(row) for row in raw];seen=set()
 for row in members:
  key=(row['group'],row['start'],row['end'])
  if row['group'] not in groups or key in seen:raise ValueError('Unknown group or duplicate alternate interval')
  seen.add(key)
 return dict(schemaVersion=1,videoID=identifier,sourceSHA256=source_sha,declaredSourceDurationSeconds=source_duration,decodedDurationSeconds=decoded_duration,analysisDurationSeconds=duration,engine='speechbrain-ecapa-silero',candidates=chosen,memberIntervals=members,alternateIntervalsAvailable='memberIntervals' in analysis,truncated=analysis.get('truncated',False),groupLimitExceeded=analysis.get('groupLimitExceeded',False),limits=dict(maxGroups=32,maxIntervals=512),identityVerified=False,cleanSpeechVerified=False,overlapAssessed=False,limitations=['tentative-grouping','speech-suitability-unreviewed','music-not-classified','overlap-not-assessed'])

def screen_transcript(text):
 """Explicit annotations request review; their absence never proves clean speech."""
 count=len(text) if isinstance(text,str) else 0
 words=len(re.findall(r'\b\w+\b',text)) if isinstance(text,str) and count<=3000 else 0
 result=dict(status='eligible-unreviewed',reason='annotations-not-observed',wordCount=words,characterCount=count,cleanSpeechVerified=False,musicClassified=False)
 if not isinstance(text,str) or not 1<=count<=3000 or words<3:
  result.update(status='review-needed',reason='insufficient-transcribed-speech')
 elif any(marker in text for marker in ('♪','♫','â™ª','â™«')) or re.search(r'[\[(]\s*(?:music|singing|instrumental|applause|laughter|silence|inaudible|unintelligible)\b[^\]\)\r\n]{0,80}[\])]',text,re.I):
  result.update(status='review-needed',reason='explicit-non-speech-annotation')
 return result

def _review_artifact(root,identifier,request_id,evidence,outcomes,cancelled,commit):
 payload=dict(schemaVersion=1,status='review-needed',videoID=identifier,requestID=request_id,sourceSHA256=evidence['sourceSHA256'],analysisEvidence=evidence,analysisEvidenceSHA256=hashlib.sha256(_canonical(evidence)).hexdigest(),candidateOutcomes=outcomes,identityVerified=False,cleanSpeechVerified=False,runnable=False)
 data=_canonical(payload);revision=hashlib.sha256(data).hexdigest()
 if len(data)>262144:raise ValueError('Review evidence exceeds bound')
 folder=root/'candidate-reviews'/identifier
 if any(p.is_symlink() for p in (folder,folder.parent)):raise ValueError('Linked review destinations are unsupported')
 folder.mkdir(parents=True,exist_ok=True)
 destination=folder/(revision+'.json')
 fd,name=tempfile.mkstemp(prefix='.review-',dir=folder)
 try:
  with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
  def publish_review():
   if cancelled():raise InterruptedError('Candidate evidence paused before commit')
   if destination.is_symlink():raise ValueError('Linked review evidence')
   try:os.link(name,destination)
   except FileExistsError:
    if destination.is_symlink() or not destination.is_file() or destination.stat().st_size!=len(data) or destination.read_bytes()!=data:raise FileExistsError('Existing review evidence preserved')
  if cancelled():raise InterruptedError('Candidate evidence paused before commit')
  if commit is None:publish_review()
  else:commit(publish_review)
 finally:pathlib.Path(name).unlink(missing_ok=True)
 return destination


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
     with wave.open(str(decoded),'rb') as decoded_audio:
      if (decoded_audio.getnchannels(),decoded_audio.getsampwidth(),decoded_audio.getframerate())!=(1,2,16000):raise ValueError('Unexpected decoded analysis audio')
      decoded_duration=decoded_audio.getnframes()/decoded_audio.getframerate()
     source_duration=source.get('duration')
     activity('speaker_analyzing');analysis=analyze(decoded,cancelled)
     if not isinstance(analysis,dict) or analysis.get('schemaVersion')!=1 or analysis.get('labelsVerified') is not False or analysis.get('speakerSeparated') is not False:raise ValueError('Invalid candidate-analysis evidence')
     evidence=analysis_evidence(analysis,source_hash,identifier,source_duration,decoded_duration)
     candidates=analysis.get('candidates')
     if not isinstance(candidates,list) or len(candidates)>32:raise ValueError('Candidate count exceeds limit')
     seen=set();audio_hashes=set();omitted=[];outcomes=[]
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
      if digest in audio_hashes:
       omitted.append(dict(group=row['group'],reason='duplicate-reference'));outcomes.append(dict(group=row['group'],status='review-needed',reason='duplicate-reference',cleanSpeechVerified=False));continue
      activity('transcribing',index,len(candidates));text=transcribe(wav)
      if cancelled():raise InterruptedError('Candidate screening paused')
      suitability=screen_transcript(text);outcomes.append(dict(group=row['group'],**suitability))
      if suitability['status']=='review-needed':
       omitted.append(dict(group=row['group'],reason=suitability['reason']));continue
      audio_hashes.add(digest);files[profile+'.wav']=data
      metadata=dict(id=profile,name='Speaker '+str(row['group']).zfill(2)+' (unreviewed)',categories=['Unreviewed speaker candidates'],source='Private video '+request['videoURL']+'; SHA-256 '+source_hash+'; segment '+str(start)+' to '+str(end)+' seconds; anonymous automatic speaker grouping, not verified character identity',permission=request['sourceUse']['record'],referenceText=text.strip())
      rows.append(dict(metadata=metadata,referenceSHA256=digest,referenceTranscriptStatus='automatic-needs-review',candidateEvidence=dict(group=row['group'],start=start,end=end,identityVerified=False,overlapExcluded=False,suitability=suitability)))
     if not rows:
      _review_artifact(root,identifier,request['requestID'],evidence,outcomes,cancelled,commit)
      raise ReviewRequired('No eligible unreviewed candidates; private source-bound evidence retained for review')
     provenance=dict(videoID=identifier,sourceURL=request['videoURL'],sourceSHA256=source_hash,requestID=request['requestID'],sourceUse=request['sourceUse'],identityVerified=False,likenessVerified=False,trainedRVC=False,analysisEngine=analysis.get('engine','unknown'),candidateLimit=32,analysisTruncated=analysis.get('truncated') is True,omitted=omitted,analysisEvidence=evidence,analysisEvidenceSHA256=hashlib.sha256(_canonical(evidence)).hexdigest(),candidateOutcomes=outcomes,candidateCounts=dict(total=len(candidates),eligibleUnreviewed=len(rows),reviewNeeded=len(candidates)-len(rows)))
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
    if cancelled():raise InterruptedError('Candidate preparation paused at commit')
    if output.exists() or output.is_symlink():raise FileExistsError('Existing prepared specification was preserved')
    os.link(name,output)
   if commit is None:publish_pointer()
   else:commit(publish_pointer)
  finally:pathlib.Path(name).unlink(missing_ok=True)
  return output
