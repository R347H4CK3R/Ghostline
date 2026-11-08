import json,unittest,hashlib,pathlib
import test_queue_processor as fixture

class ListeningTests(unittest.TestCase):
 setUp=fixture.ProcessorTests.setUp
 tearDown=fixture.ProcessorTests.tearDown
 run_job=fixture.ProcessorTests.run_job
 synth=fixture.ProcessorTests.synth
 # Reuse only the real synthetic processor fixture, not its test methods.
 def api(self):
  from tools.listening_review import ListeningReview
  return ListeningReview(self.root/'work',self.root/'queue.db')
 def row(self):self.run_job();return self.api().catalog()['candidates'][0]
 def body(self,row,decision='Unsure'):
  return dict(videoID=row['videoID'],attempt=row['attempt'],profileIndex=row['profileIndex'],snapshot=row['snapshot'],decision=decision,reviewer='Fixture reviewer',note='Original fixture test')
 def test_snapshot_exposes_checked_reference_and_preview(self):
  row=self.row();api=self.api()
  for kind,key in [('reference','referenceSHA256'),('preview','generatedSHA256')]:self.assertEqual(hashlib.sha256(api.audio(row['videoID'],row['attempt'],row['profileIndex'],row['snapshot'],kind)).hexdigest(),row[key])
 def test_all_three_explicit_decisions_are_durable_without_activation(self):
  row=self.row();master=self.root/'Voices';before={str(p):p.read_bytes() for p in master.rglob('*') if p.is_file()}
  for decision in ['Matches','DoesntMatch','Unsure']:self.api().decide(self.body(row,decision))
  history=self.api().catalog()['candidates'][0]['reviews'];self.assertEqual([r['decision'] for r in history],['Matches','DoesntMatch','Unsure'])
  self.assertEqual(self.q.export()['videos'][0]['status'],'needs-review');self.assertEqual(before,{str(p):p.read_bytes() for p in master.rglob('*') if p.is_file()})
 def test_stale_audio_or_unchecked_decision_never_records_review(self):
  row=self.row();body=self.body(row);body['decision']='';
  with self.assertRaises(ValueError):self.api().decide(body)
  preview=self.root/'work/EAT0nWoEzJ8/attempt-1/synthetic-original-preview.wav';preview.write_bytes(b'corrupt')
  with self.assertRaises(ValueError):self.api().decide(self.body(row,'Matches'))
 def test_terminal_or_failed_queue_job_cannot_be_approved(self):
  row=self.row()
  with self.q.db:self.q.db.execute("UPDATE jobs SET status='failed'")
  with self.assertRaises(ValueError):self.api().decide(self.body(row,'Matches'))
 def test_real_http_auth_csrf_asset_and_durable_decision(self):
  import shutil,threading,urllib.request,urllib.error,re
  from tools.queue_transport import create_server
  row=self.row();shutil.move(str(self.root/'work/EAT0nWoEzJ8'),self.root/'EAT0nWoEzJ8')
  server=create_server(self.root,'s'*48);threading.Thread(target=server.serve_forever,daemon=True).start()
  def request(path,body=None,auth=True,nonce=None):
   headers={'Authorization':'Bearer '+'s'*48} if auth else {}
   if body is not None:headers['Content-Type']='application/json'
   if nonce:headers['X-VoiceMatrix-Review']=nonce
   req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
   try:
    with urllib.request.urlopen(req) as r:return r.status,r.read()
   except urllib.error.HTTPError as r:return r.code,r.read()
  try:
   self.assertEqual(request('/listening',auth=False)[0],401)
   code,page=request('/listening');self.assertEqual(code,200);nonce=re.search(rb'const csrf="([a-zA-Z0-9_-]+)"',page).group(1).decode()
   body=self.body(row);self.assertEqual(request('/listening/decisions',body)[0],403)
   self.assertEqual(request('/listening/decisions',body,nonce=nonce)[0],200)
   data=json.loads(request('/listening/catalog')[1]);self.assertEqual(data['candidates'][0]['reviews'][0]['decision'],'Unsure')
   asset='/listening/assets/EAT0nWoEzJ8/1/0/'+row['snapshot']+'/preview'
   self.assertEqual(hashlib.sha256(request(asset)[1]).hexdigest(),row['generatedSHA256']);self.assertEqual(request(asset,auth=False)[0],401)
   self.assertEqual(request('/listening/assets/../../queue.db')[0],404)
  finally:server.shutdown();server.server_close()
 def test_malformed_reports_are_visible_errors_without_false_review(self):
  row=self.row();path=self.root/'work/EAT0nWoEzJ8/attempt-1/result.json';original=json.loads(path.read_text())
  for bad in [[],dict(original,profiles=[dict(original['profiles'][0],wordcheck=[])])]:
   path.write_text(json.dumps(bad));result=self.api().catalog();self.assertEqual(result['candidates'],[]);self.assertEqual(len(result['errors']),1)
   with self.assertRaises(ValueError):self.api().decide(self.body(row))
 def test_valid_twenty_second_processor_preview_remains_reviewable(self):
  import wave
  row=self.row();folder=self.root/'work/EAT0nWoEzJ8/attempt-1';preview=folder/'synthetic-original-preview.wav'
  with wave.open(str(preview),'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b'\x00\x08'*(24000*20))
  p=folder/'result.json';result=json.loads(p.read_text());sha=hashlib.sha256(preview.read_bytes()).hexdigest();result['profiles'][0]['audio']['wavSHA256']=sha;result['profiles'][0]['wordcheck']['wavSHA256']=sha;p.write_text(json.dumps(result))
  self.assertEqual(self.api().catalog()['candidates'][0]['generatedSHA256'],sha)
 def test_old_asset_rejects_no_longer_pending_job(self):
  row=self.row()
  with self.q.db:self.q.db.execute("UPDATE jobs SET status='failed'")
  with self.assertRaises(ValueError):self.api().audio(row['videoID'],row['attempt'],row['profileIndex'],row['snapshot'],'preview')
 def test_unsupported_zip_entry_becomes_per_job_diagnostic(self):
  import struct,zipfile
  self.row();path=self.root/'work/EAT0nWoEzJ8/attempt-1/profile-0.vmpack';data=bytearray(path.read_bytes())
  with zipfile.ZipFile(path) as z:offset=z.infolist()[0].header_offset
  struct.pack_into('<H',data,offset+8,99);struct.pack_into('<H',data,data.index(b'PK\x01\x02')+10,99);path.write_bytes(data)
  result=self.api().catalog();self.assertEqual(result['candidates'],[]);self.assertEqual(len(result['errors']),1)
