"""Bounded catalog observations for authenticated live logs, never a voice publisher.

Only safe display names, opaque IDs, times and change kinds leave this module.
An observation time is not a publication time. History is memory-only and starts
again when the companion restarts; an initial list is never called newly added.
"""
import copy, hashlib, json, math, re, threading, time, unicodedata


def safe_name(value):
 if not isinstance(value,str) or not 1<=len(value)<=120 or len(value.encode('utf8'))>160:return 'Name hidden'
 if any(unicodedata.category(c).startswith('C') for c in value):return 'Name hidden'
 if any(c in value for c in '/\\:=<>@') or re.search(r'(?i)\b(bearer|token|password|secret|api[ _-]?key)\b',value):return 'Name hidden'
 if re.search(r'[A-Za-z0-9_-]{32,}',value):return 'Name hidden'
 return value.strip() or 'Name hidden'


class CatalogActivity:
 def __init__(self):
  self.lock=threading.Lock();self.voices={};self.fingerprints={};self.events=[];self.sequence=0
  self.checked_at=None;self.changed_at=None;self.state='not_checked';self.running=False;self.last_attempt=None
 def observe(self,catalog,*,now=None):
  now=time.time() if now is None else now
  if type(now) not in (int,float) or not math.isfinite(now) or not 0<=now<=253402300799:raise ValueError('Invalid observation time')
  rows=catalog.get('voices')
  if not isinstance(rows,list) or len(rows)>1000:raise ValueError('Invalid catalog observation')
  incoming={};fingerprints={}
  for row in rows:
   identifier=row.get('id') if isinstance(row,dict) else None
   if not isinstance(identifier,str) or not re.fullmatch(r'[a-z0-9_-]{1,100}',identifier):raise ValueError('Invalid catalog voice')
   key=hashlib.sha256(identifier.encode()).hexdigest()
   if key in incoming:raise ValueError('Duplicate catalog voice')
   incoming[key]=dict(id=key,name=safe_name(row.get('name')))
   # Retain only a digest of content, never reference words, paths or credentials.
   fingerprints[key]=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
  with self.lock:
   initial=self.checked_at is None
   for key,row in incoming.items():
    previous=self.voices.get(key)
    changed=previous is None or fingerprints[key]!=self.fingerprints.get(key)
    row['firstObservedAt']=previous['firstObservedAt'] if previous else now
    row['lastChangedAt']=now if changed else previous['lastChangedAt']
    if changed:self._event('observed' if initial else 'added' if previous is None else 'changed',row,now)
   for key,row in self.voices.items():
    if key not in incoming:self._event('missing',row,now)
   self.voices=incoming;self.fingerprints=fingerprints;self.checked_at=now;self.state='current'
 def _event(self,kind,row,now):
  self.sequence+=1;self.changed_at=now
  self.events.append(dict(sequence=self.sequence,time=now,kind=kind,voiceID=row['id'],name=row['name']))
  self.events=self.events[-160:]
 def failed(self):
  with self.lock:self.state='unavailable'
 def refresh(self,provider):
  """Nonblocking single-flight checks, no more than once per 30 seconds.

  Provider must return a validated private catalog. It reads the existing master;
  this observer cannot change the collection or download anything to the phone.
  """
  with self.lock:
   now=time.monotonic()
   if self.running or (self.last_attempt is not None and now-self.last_attempt<30):return
   self.running=True;self.last_attempt=now;self.state='checking'
  def check():
   try:self.observe(provider())
   except Exception:self.failed() # Raw errors can contain private paths or text.
   finally:
    with self.lock:self.running=False
  threading.Thread(target=check,name='catalog-observation',daemon=True).start()
 def snapshot(self):
  with self.lock:
   return dict(schemaVersion=1,state=self.state,count=len(self.voices),checkedAt=self.checked_at,
               lastChangedAt=self.changed_at,voices=copy.deepcopy(list(self.voices.values())),
               events=copy.deepcopy(self.events))
