"""Initial reviewed recipes only; no inferred identity, permission or replacement approval."""
import json,os,pathlib,tempfile
from contextlib import contextmanager
from tools.source_inspection import validate_request,read_index
from tools.video_prepare import validate_recipe
from tools.video_queue import VideoQueue
from tools.master_voices import _publish_lock

def save_initial_review(root,recipe):
 identifier,_=validate_recipe(recipe,transcribe_available=True)
 if set(recipe)-{'schemaVersion','videoURL','referenceUseReview','segments','inspectionRevision','inspectedSourceSHA256'}:raise ValueError('Unsupported review fields')
 if 'inspectionRevision' in recipe:
  index=read_index(root,identifier)
  if recipe['inspectionRevision']!=index['revision'] or recipe['inspectedSourceSHA256']!=index['sourceSHA256']:raise ValueError('Inspected source revision changed; refresh previews')
 data=(json.dumps(recipe,ensure_ascii=False,indent=2)+'\n').encode()
 if len(data)>512000:raise ValueError('Review is too large')
 root=pathlib.Path(root).resolve();folder=root/'recipes'
 if folder.is_symlink():raise ValueError('Linked recipe directory is unsupported')
 folder.mkdir(exist_ok=True)
 with _publish_lock(root/'.source-review.lock'):
  q=VideoQueue(str(root/'queue.db'))
  try:
   q.db.execute('BEGIN IMMEDIATE')
   job=next((v for v in q.export()['videos'] if v['id']==identifier),None)
   if job is None or job['status'] not in ['waiting','awaiting-preparation','paused']:raise ValueError('Only waiting initial preparation jobs can be reviewed')
   if (root/'specifications'/(identifier+'.json')).exists():raise FileExistsError('This video is already prepared')
   output=folder/(identifier+'.json')
   if output.exists() or output.is_symlink():raise FileExistsError('A reviewed recipe already exists; replacement review is not supported here')
   fd,name=tempfile.mkstemp(prefix='.review-',dir=folder)
   try:
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(name,output)
   finally:pathlib.Path(name).unlink(missing_ok=True)
   q.db.commit()
  finally:q.close()
 return dict(status='awaiting-preparation',videoID=identifier,likenessVerified=False,completed=False)

def page(csrf):
 html=pathlib.Path(__file__).with_name('source_review.html').read_text(encoding='utf8')
 return html.replace('__CSRF__',csrf).encode()

@contextmanager
def initial_job(root,identifier):
 root=pathlib.Path(root).resolve()
 with _publish_lock(root/'.source-review.lock'):
  q=VideoQueue(str(root/'queue.db'))
  try:
   q.db.execute('BEGIN IMMEDIATE')
   job=next((v for v in q.export()['videos'] if v['id']==identifier),None)
   if job is None or job['status'] not in ['waiting','awaiting-preparation','paused']:raise ValueError('Only initial waiting jobs may request inspection')
   if any((root/folder/(identifier+'.json')).exists() for folder in ['recipes','specifications']):raise FileExistsError('Saved preparation was preserved')
   yield root
   q.db.commit()
  finally:q.close()

def save_inspection(root,request):
 identifier=validate_request(request)
 data=(json.dumps(request,ensure_ascii=False,indent=2)+'\n').encode()
 if len(data)>16384:raise ValueError('Inspection request too large')
 with initial_job(root,identifier) as root:
  folder=root/'inspections'
  if folder.is_symlink():raise ValueError('Linked inspection folder unsupported')
  folder.mkdir(exist_ok=True);output=folder/(identifier+'.json')
  if output.is_symlink():raise ValueError('Linked inspection request unsupported')
  if output.exists():
   if output.stat().st_size>16384 or json.loads(output.read_bytes())!=request:raise FileExistsError('An inspection use record already exists')
  else:
   fd,name=tempfile.mkstemp(prefix='.inspection-',dir=folder)
   try:
    with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    os.replace(name,output)
   finally:pathlib.Path(name).unlink(missing_ok=True)
  output.with_suffix('.cancel').unlink(missing_ok=True)
 return dict(status='inspection-requested',videoID=identifier,likenessVerified=False)

def stop_inspection(root,body):
 import re
 if not isinstance(body,dict) or set(body)!={'videoID'} or not isinstance(body['videoID'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',body['videoID']):raise ValueError('Invalid inspection selection')
 root=pathlib.Path(root).resolve();folder=root/'inspections'
 if folder.is_symlink():raise ValueError('Linked inspection folder unsupported')
 path=folder/(body['videoID']+'.json')
 if not path.is_file() or path.is_symlink():raise ValueError('No inspection request')
 with _publish_lock(root/'.source-review.lock'):
  marker=path.with_suffix('.cancel')
  if marker.is_symlink():raise ValueError('Linked stop marker unsupported')
  with marker.open('wb') as f:f.write(b'stop\n');f.flush();os.fsync(f.fileno())
 return dict(status='stop-requested',videoID=body['videoID'])
