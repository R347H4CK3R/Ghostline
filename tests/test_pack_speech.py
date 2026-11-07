import pathlib,tempfile,unittest,wave
from tools.voice_pack import export_reference_pack
from tools.pack_speech import speak

class PackSpeechTests(unittest.TestCase):
 def test_selected_reference_and_text_reach_engine(self):
  with tempfile.TemporaryDirectory() as d:
   root=pathlib.Path(d);reference=root/'source.wav'
   with wave.open(str(reference),'wb') as w:w.setparams((1,2,24000,0,'NONE','none'));w.writeframes(b'\0\x10'*24000)
   pack=export_reference_pack(reference,dict(id='one',name='One',source='Original recording',permission='Creator consent',referenceText='Reference words',categories=['Fantasy']),root/'one.vmpack')
   class Engine:
    def infer(self,**kwargs):
     self.args=kwargs;self.reference=pathlib.Path(kwargs['ref_file']);assert self.reference.exists()
     return [0.1,-0.1]*12000,24000,None
   engine=Engine();result=speak(pack,'New words',root/'output.wav',engine)
   self.assertEqual(engine.args['ref_text'],'Reference words');self.assertEqual(engine.args['gen_text'],'New words')
   self.assertFalse(engine.reference.exists());self.assertEqual(result['profileID'],'one')
   with wave.open(str(root/'output.wav')) as w:self.assertEqual(w.getnframes(),24000)
 def test_empty_text_rejected_before_engine(self):
  with self.assertRaises(ValueError):speak('missing.vmpack',' ','unused.wav',None)

if __name__=='__main__':unittest.main()
