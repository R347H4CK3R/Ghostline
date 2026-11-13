"""Executable native numerical contract; no trained model or voice likeness claim."""
import ctypes as C
import math
import random
import pathlib
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).parent
class FeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        lib=pathlib.Path(cls.tmp.name)/'features.so'
        subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'features.cpp'),'-o',str(lib)],check=True)
        cls.lib=C.CDLL(str(lib))
        cls.lib.rvc_prepare_features.argtypes=[C.POINTER(C.c_float),C.POINTER(C.c_float),C.c_size_t,C.c_size_t,C.POINTER(C.c_float),C.c_size_t,C.c_float,C.POINTER(C.c_float),C.POINTER(C.c_int64)]
        cls.lib.rvc_prepare_features.restype=C.c_int
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def call(self,a,b,p,protect=.33,frames=2,channels=2):
        arr=lambda x:(C.c_float*len(x))(*x)
        out=arr([-999]*(len(p)*channels)); bins=(C.c_int64*len(p))(*([-999]*len(p)))
        ok=self.lib.rvc_prepare_features(arr(a),arr(b),frames,channels,arr(p),len(p),protect,out,bins)
        return ok,list(out),list(bins)
    def test_nearest_double_rate_and_protection(self):
        ok,out,bins=self.call([1,2,3,4],[11,12,13,14],[0,100,0,1100])
        self.assertEqual(ok,1)
        for a,b in zip(out,[4.3,5.3,11,12,6.3,7.3,13,14]):self.assertAlmostEqual(a,b,places=5)
        expected=[1]+[round((1127*math.log1p(h/700)-1127*math.log1p(50/700))*254/(1127*math.log1p(1100/700)-1127*math.log1p(50/700))+1) for h in [100]]+[1,255]
        self.assertEqual(bins,expected)
    def test_no_retrieval_and_full_protection_disabled(self):
        for protection in [.5,1.0]:
            ok,out,bins=self.call([1,2,3,4],[11,12,13,14],[0,50,1100,2000],protection)
            self.assertEqual(ok,1);self.assertEqual(out,[11,12,11,12,13,14,13,14]);self.assertEqual(bins,[1,1,255,255])
    def test_invalid_inputs_leave_both_outputs_untouched(self):
        for pitch in [[0,float('nan'),0,100],[0,-1,0,100],[0,float('inf'),0,100]]:
            ok,out,bins=self.call([1,2,3,4],[11,12,13,14],pitch)
            self.assertEqual(ok,0);self.assertEqual(out,[-999]*8);self.assertEqual(bins,[-999]*4)
        for protect in [-1,float('nan'),1.1]:
            self.assertEqual(self.call([1,2,3,4],[11,12,13,14],[0,100,0,100],protect)[0],0)
        for a in [[1,float('nan'),3,4],[1,2,float('inf'),4]]:
            self.assertEqual(self.call(a,[1,2,3,4],[0,100,0,100])[0],0)
    def test_maximum_shape_against_independent_reference(self):
        rng=random.Random(17)
        a=[rng.uniform(-3,3) for _ in range(500*768)]
        b=[rng.uniform(-3,3) for _ in a]
        p=[rng.choice([0,.5,50,100,220,440,1100,1500]) for _ in range(1000)]
        ok,out,bins=self.call(a,b,p,frames=500,channels=768)
        self.assertEqual(ok,1)
        for i,hz in enumerate(p):
            w=C.c_float(.33).value if hz<1 else 1
            for j in [0,10,400,767]:
                k=(i//2)*768+j
                expected=C.c_float(b[k]).value*w+C.c_float(a[k]).value*(1-w)
                self.assertAlmostEqual(out[i*768+j],expected,places=5)
            mel=1127*math.log1p(hz/700)
            low=1127*math.log1p(50/700);high=1127*math.log1p(1100/700)
            expected=round(min(255,max(1,(mel-low)*254/(high-low)+1))) if hz else 1
            self.assertEqual(bins[i],expected)
    def test_null_and_oversized_contract_rejected_before_access(self):
        x=(C.c_float*1)(3); y=(C.c_int64*1)(4)
        f=self.lib.rvc_prepare_features
        for frames,channels,count in [(0,1,0),(501,1,1002),(1,769,2)]:
            self.assertEqual(f(x,x,frames,channels,x,count,.33,x,y),0)
            self.assertEqual(x[0],3);self.assertEqual(y[0],4)
        self.assertEqual(f(None,x,1,1,x,2,.33,x,y),0)

    def test_wrong_frame_count_rejected_transactionally(self):
        ok,out,bins=self.call([1,2,3,4],[11,12,13,14],[100,100,100])
        self.assertEqual(ok,0);self.assertEqual(out,[-999]*6);self.assertEqual(bins,[-999]*3)

if __name__=='__main__':unittest.main()
