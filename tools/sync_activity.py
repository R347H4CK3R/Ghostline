"""Bounded, memory-only sync evidence. Never retain voice paths, text, audio or credentials."""
import collections, copy, datetime, hashlib, threading, time, uuid

class SyncActivity:
 def __init__(self):
  self.lock=threading.Lock();self.sessions=collections.OrderedDict()
 def _prune(self):
  now=time.monotonic()
  for key in list(self.sessions):
   if now-self.sessions[key]['updated']>900:del self.sessions[key]
  while len(self.sessions)>32:self.sessions.popitem(last=False)
 def start(self,identifier):
  identifier=identifier or str(uuid.uuid4())
  try:
   if str(uuid.UUID(identifier))!=identifier:raise ValueError('Invalid sync ID')
  except (ValueError,AttributeError):raise ValueError('Invalid sync ID')
  with self.lock:
   self._prune()
   if identifier in self.sessions:raise ValueError('Sync ID already used')
   self.sessions[identifier]=dict(updated=time.monotonic(),events=[],sequence=0,files=set())
   self._prune()
  self.add(identifier,'received');return identifier
 def add(self,identifier,stage,completed=0,total=0,byte_count=0,file_key=None):
  if identifier is None:return
  with self.lock:
   self._prune();session=self.sessions.get(identifier)
   if session is None:return
   if file_key is not None:
    if len(session['files'])<2001:session['files'].add(hashlib.sha256(file_key.encode()).digest())
    completed=len(session['files'])
   session['sequence']+=1;session['updated']=time.monotonic()
   session['events'].append(dict(sequence=session['sequence'],time=datetime.datetime.now(datetime.timezone.utc).isoformat(),stage=stage,completed=completed,total=total,bytes=byte_count))
   session['events']=session['events'][-160:]
 def snapshot(self,identifier=None):
  with self.lock:
   self._prune()
   def public(key,value):return dict(schemaVersion=1,syncID=key,events=copy.deepcopy(value['events']))
   if identifier is not None:
    value=self.sessions.get(identifier)
    return public(identifier,value) if value else None
   return dict(schemaVersion=1,sessions=[public(k,v) for k,v in reversed(self.sessions.items())])

def page(nonce):
 return ('''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>VoiceMatrix sync log</title>
<style nonce="NONCE">body{font:16px system-ui;background:#10141d;color:#edf3fa;max-width:850px;margin:auto;padding:24px}article{border:1px solid #465269;border-radius:16px;padding:16px;margin:16px 0}li{margin:10px 0}small{color:#bac7d8}</style>
<h1>Live voice sync log</h1><p>Actual requests received by this laptop. Refreshes every second. File responses sent do not prove the phone has saved them.</p><p id="state" role="status">Checking…</p><main id="sessions"></main>
<script nonce="NONCE">
const names={received:'Laptop received catalog request',validating:'Laptop checking private collection',validated:'Laptop validated voice references',catalog_ready:'Laptop prepared catalog',catalog_sent:'Laptop sent catalog',file_sent:'Laptop sent voice file response',failed:'Laptop could not serve the snapshot',disconnected:'Connection closed before response finished'};
async function refresh(){try{const response=await fetch('/voice-sync',{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();document.querySelector('#state').textContent=data.sessions.length?'Connected · latest laptop activity below':'Connected · no sync request received since this companion started';const host=document.querySelector('#sessions');host.replaceChildren();for(const session of data.sessions){const article=document.createElement('article');const title=document.createElement('h2');title.textContent='Sync '+session.syncID.slice(0,8);article.append(title);const list=document.createElement('ol');for(const event of session.events){const item=document.createElement('li');item.textContent=new Date(event.time).toLocaleTimeString()+' · '+(names[event.stage]||'Activity')+(event.total?' · '+event.completed+'/'+event.total:'')+(event.bytes?' · '+event.bytes.toLocaleString()+' bytes':'');list.append(item)}article.append(list);host.append(article)}}catch{document.querySelector('#state').textContent='Cannot refresh laptop activity. Check Tailscale and companion connection.'}finally{setTimeout(refresh,1000)}}refresh();
</script><small>Private to this authenticated connection. Keeps up to 32 recent syncs for 15 minutes in memory. No voice names, recordings or transcripts are logged.</small>''').replace('NONCE',nonce).encode()
