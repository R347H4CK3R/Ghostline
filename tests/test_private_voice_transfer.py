import hashlib,json,pathlib,tempfile,threading,unittest,urllib.request,urllib.error,wave,shutil,os,subprocess
from tools.queue_transport import create_server
from tools.voice_pack import export_reference_pack,export_collection_folder

class PrivateTransferTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  audio=self.root/'reference.wav'
  with wave.open(str(audio),'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(b'\x00\x10'*24000)
  metadata=dict(id='original-test',name='Private fixture',categories=['Original & Comedy'],source='Synthetic fixture',permission='Synthetic local test only',referenceText='A reference sentence.')
  pack=export_reference_pack(audio,metadata,self.root/'voice.vmpack');export_collection_folder([pack],self.root/'Voices')
  self.server=create_server(self.root/'endpoint','x'*48,master=self.root/'Voices');self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):
  if hasattr(self,'server'):self.server.shutdown();self.server.server_close();self.thread.join()
  self.tmp.cleanup()
 def get(self,path,authorized=True):
  request=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+path,headers={'Authorization':'Bearer '+'x'*48} if authorized else {})
  return urllib.request.urlopen(request,timeout=5)
 def test_authorized_snapshot_reconstructs_exact_native_folder(self):
  with self.get('/voices') as r:
   self.assertEqual(r.headers['Cache-Control'],'no-store');catalog=json.load(r)
  self.assertEqual(catalog['schemaVersion'],1);self.assertEqual(len(catalog['files']),3)
  for row in catalog['files']:
   with self.get('/voices/'+catalog['revision']+'/'+row['path']) as r:data=r.read()
   self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256']);self.assertEqual(len(data),row['bytes'])
   self.assertEqual(data,(self.root/'Voices'/row['path']).read_bytes())
 def test_anonymous_cannot_read_catalog_or_reference(self):
  for path in ['/voices','/voices/'+'a'*64+'/original-test/reference.wav']:
   with self.assertRaises(urllib.error.HTTPError) as e:self.get(path,False)
   self.assertEqual(e.exception.code,401)
 def test_unknown_paths_and_old_snapshot_do_not_read_arbitrary_files(self):
  with self.get('/voices') as r:catalog=json.load(r)
  for path in ['../reference.wav','original-test/../../reference.wav','original-test/manifest.json?extra=true']:
   with self.assertRaises(urllib.error.HTTPError) as e:self.get('/voices/'+catalog['revision']+'/'+path)
   self.assertEqual(e.exception.code,404)
  with self.assertRaises(urllib.error.HTTPError) as e:self.get('/voices/'+'0'*64+'/collection.json')
  self.assertEqual(e.exception.code,409)
 def test_changed_source_bytes_never_sent_under_previous_hash(self):
  with self.get('/voices') as r:catalog=json.load(r)
  (self.root/'Voices/original-test/reference.wav').write_bytes(b'private unrelated bytes')
  with self.assertRaises(urllib.error.HTTPError) as e:self.get('/voices/'+catalog['revision']+'/original-test/reference.wav')
  self.assertEqual(e.exception.code,409)
 def test_unconfigured_endpoint_does_not_expose_a_default_directory(self):
  other=create_server(self.root/'unconfigured','x'*48);thread=threading.Thread(target=other.serve_forever,daemon=True);thread.start()
  try:
   req=urllib.request.Request('http://127.0.0.1:'+str(other.server_port)+'/voices',headers={'Authorization':'Bearer '+'x'*48})
   with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
   self.assertEqual(e.exception.code,404)
  finally:other.shutdown();other.server_close();thread.join()

 def test_replaced_master_ancestor_cannot_serve_another_folder(self):
  from tools.private_voices import PrivateVoices,TransferError
  selected=self.root/'selected';outside=self.root/'outside';selected.mkdir();outside.mkdir()
  shutil.copytree(self.root/'Voices',selected/'Voices');shutil.copytree(self.root/'Voices',outside/'Voices')
  source=PrivateVoices(selected/'Voices');source.catalog();selected.rename(self.root/'selected-old')
  if os.name=='nt':subprocess.run(['cmd','/c','mklink','/J',str(selected),str(outside)],check=True,capture_output=True)
  else:selected.symlink_to(outside,target_is_directory=True)
  with self.assertRaises(TransferError):source.catalog()

if __name__=='__main__':unittest.main()
