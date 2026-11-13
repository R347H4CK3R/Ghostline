import ctypes as C,pathlib,subprocess,tempfile,unittest,math
ROOT=pathlib.Path(__file__).parent
class Pitch(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=pathlib.Path(cls.tmp.name)/'pitch.so'
  subprocess.run(['c++','-std=c++17','-shared','-fPIC',str(ROOT/'Runner/pitch.cpp'),'-o',str(p)],check=True);cls.lib=C.CDLL(str(p))
  F=C.POINTER(C.c_float)
  cls.lib.rvc_pitch_frames.argtypes=[F,C.c_size_t,C.c_size_t,C.c_size_t,F,F];cls.lib.rvc_pitch_frames.restype=C.c_int
  cls.lib.rvc_pitch_decode.argtypes=[F,C.c_size_t,F,C.c_float,C.c_float,C.c_float,C.c_float,F,F];cls.lib.rvc_pitch_decode.restype=C.c_int
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_zero_centered_framing_and_sample_standard_deviation(self):
  a=[.2*math.sin(2*math.pi*220*i/16000) for i in range(1600)];audio=(C.c_float*len(a))(*a);out=(C.c_float*(2*1024))();rms=(C.c_float*2)()
  self.assertEqual(self.lib.rvc_pitch_frames(audio,len(a),0,2,out,rms),1)
  for frame in range(2):
   raw=[audio[j] if 0<=j<len(a) else 0.0 for j in range(frame*160-512,frame*160+512)];mean=sum(raw)/1024;std=math.sqrt(sum((v-mean)**2 for v in raw)/1023)
   for j in range(1024):self.assertAlmostEqual(out[frame*1024+j],(raw[j]-mean)/std,places=5)
 def test_decoder_voiced_silent_lowconfidence(self):
  vals=[0.0]*(3*360);vals[168]=.9;vals[360+168]=.9;vals[720+168]=.05
  sal=(C.c_float*len(vals))(*vals);energy=(C.c_float*3)(.1,0,.1);pitch=(C.c_float*3)();conf=(C.c_float*3)()
  self.assertEqual(self.lib.rvc_pitch_decode(sal,3,energy,50,1100,.1,.001,pitch,conf),1)
  self.assertAlmostEqual(pitch[0],10*2**((20*168+1997.3794084376191)/1200),places=4);self.assertEqual(list(pitch)[1:],[0,0])
 def test_dc_only_frame_has_zero_ac_energy(self):
  audio=(C.c_float*8000)(*([.2]*8000));out=(C.c_float*1024)();energy=(C.c_float*1)()
  self.assertEqual(self.lib.rvc_pitch_frames(audio,8000,10,1,out,energy),1)
  self.assertEqual(energy[0],0);self.assertTrue(all(v==0 for v in out))
 def test_bounds_and_overlapping_outputs_rejected(self):
  audio=(C.c_float*1)(0);out=(C.c_float*1024)();energy=(C.c_float*1)()
  for samples,first,count in [(48001,0,1),(1,1,1),(1,0,17),(0,0,1)]:
   self.assertEqual(self.lib.rvc_pitch_frames(audio,samples,first,count,out,energy),0)
  self.assertEqual(self.lib.rvc_pitch_frames(audio,1,0,1,out,out),0)
  self.assertEqual(self.lib.rvc_pitch_frames(audio,1,0,1,out,energy),1)
  self.assertTrue(all(v==0 for v in out))
 def test_invalid_input_is_transactional(self):
  audio=(C.c_float*1600)(*([float('nan')]+[0]*1599));out=(C.c_float*1024)(*([-9]*1024));rms=(C.c_float*1)(-9)
  self.assertEqual(self.lib.rvc_pitch_frames(audio,1600,0,1,out,rms),0);self.assertEqual(out[0],-9);self.assertEqual(rms[0],-9)
  sal=(C.c_float*360)(*([-1]+[0]*359));energy=(C.c_float*1)(.1);pitch=(C.c_float*1)(-9);conf=(C.c_float*1)(-9)
  self.assertEqual(self.lib.rvc_pitch_decode(sal,1,energy,50,1100,.1,.001,pitch,conf),0);self.assertEqual(pitch[0],-9);self.assertEqual(conf[0],-9)
if __name__=='__main__':unittest.main()
