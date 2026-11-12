"""Small stdlib fixtures for effective audio and extracted array admission gates."""
import array
import hashlib
import pathlib
import struct
import sys
import tempfile
import unittest
from tools import rvc_preprocess as prep


def float_wav(path,rate=40000,seconds=1,value=.1):
 samples=array.array('f',[value])*int(rate*seconds)
 if sys.byteorder!='little':samples.byteswap()
 pcm=samples.tobytes();fmt=struct.pack('<HHIIHH',3,1,rate,rate*4,4,32)
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_bytes(b'RIFF'+struct.pack('<I',36+len(pcm))+b'WAVEfmt '+struct.pack('<I',16)+fmt+b'data'+struct.pack('<I',len(pcm))+pcm)


def npy(path,shape,kind='<f4',value=.1):
 count=1
 for size in shape:count*=size
 header=repr(dict(descr=kind,fortran_order=False,shape=shape)).encode()+b'\n'
 types={'<f4':('f',4),'<f8':('d',8),'<i8':('q',8)}
 code,size=types[kind];data=struct.pack('<'+code,value)*count
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_bytes(b'\x93NUMPY\x01\x00'+struct.pack('<H',len(header))+header+data)


class EffectiveAudioTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve()
 def pair(self,name,seconds=3.7,value=.1):
  for folder,rate in [('0_gt_wavs',40000),('1_16k_wavs',16000)]:float_wav(self.root/folder/name,rate,seconds,value)
 def test_overlap_adjusted_active_floor_blocks_short_data(self):
  for i in range(17):self.pair(f'{i}_0.wav')
  report=prep.audit_preprocessed(self.root)
  self.assertEqual(report['status'],'insufficient-effective-data')
  self.assertAlmostEqual(report['activeSeconds'],62.9,places=3)
  self.assertAlmostEqual(report['activeLowerBoundSeconds'],57.8,places=3)
 def test_sufficient_effective_float_audio(self):
  for i in range(18):self.pair(f'{i}_0.wav')
  report=prep.audit_preprocessed(self.root)
  self.assertEqual(report['status'],'ready-for-features')
  self.assertEqual(report['fileCount'],18)
  self.assertAlmostEqual(report['activeLowerBoundSeconds'],61.2,places=3)
 def test_missing_resampled_output_rejected(self):
  self.pair('0_0.wav');(self.root/'1_16k_wavs/0_0.wav').unlink()
  with self.assertRaisesRegex(ValueError,'matching'):prep.audit_preprocessed(self.root)
 def test_empty_output_directory_rejected(self):
  with self.assertRaises(ValueError):prep.audit_preprocessed(self.root)
 def test_malformed_and_nonfinite_float_audio_rejected(self):
  for value in [float('nan'),float('inf')]:
   with self.subTest(value=value):
    self.pair('0_0.wav',value=value)
    with self.assertRaisesRegex(ValueError,'finite'):prep.audit_preprocessed(self.root)
  self.pair('0_0.wav');p=self.root/'0_gt_wavs/0_0.wav';p.write_bytes(p.read_bytes()[:-4])
  with self.assertRaises(ValueError):prep.audit_preprocessed(self.root)
 def test_silence_does_not_meet_active_floor(self):
  for i in range(18):self.pair(f'{i}_0.wav',value=0)
  report=prep.audit_preprocessed(self.root)
  self.assertEqual(report['activeLowerBoundSeconds'],0)
  self.assertEqual(report['status'],'insufficient-effective-data')

 def test_sampler_ineligible_chunks_do_not_count_toward_floor(self):
  for i in range(130):self.pair(f'{i}_0.wav',seconds=.5)
  report=prep.audit_preprocessed(self.root)
  self.assertEqual(report['retainedFileCount'],0)
  self.assertEqual(report['excludedFileCount'],130)
  self.assertEqual(report['activeLowerBoundSeconds'],0)
  self.assertEqual(report['status'],'insufficient-effective-data')
 def test_entire_missing_source_is_rejected(self):
  self.pair('0_0.wav')
  with self.assertRaisesRegex(ValueError,'source'):prep.audit_preprocessed(self.root,expected_sources=2)
 def test_before_training_requires_real_matching_arrays(self):
  for i in range(18):self.pair(f'{i}_0.wav')
  with self.assertRaises(ValueError):prep.audit_preprocessed(self.root,validate_features=True)

 def test_final_feature_alignment_is_hash_bound(self):
  for i in range(18):
   name=f'0_{i}.wav';self.pair(name)
   npy(self.root/'3_feature768'/f'0_{i}.npy',(185,768))
   npy(self.root/'2a_f0'/(name+'.npy'),(370,),'<i8',100)
   npy(self.root/'2b-f0nsf'/(name+'.npy'),(370,),'<f4',150)
  report=prep.audit_preprocessed(self.root,expected_sources=1,validate_features=True)
  self.assertEqual(report['status'],'ready-for-training')
  self.assertEqual(report['retainedFileCount'],18)
  self.assertEqual(report['files'][0]['trainingFrames'],370)
  self.assertEqual(report['files'][0]['featureSHA256'],hashlib.sha256((self.root/'3_feature768/0_0.npy').read_bytes()).hexdigest())
 def test_short_features_cannot_count_trimmed_audio(self):
  for i in range(18):
   name=f'0_{i}.wav';self.pair(name)
   npy(self.root/'3_feature768'/f'0_{i}.npy',(10,768))
   npy(self.root/'2a_f0'/(name+'.npy'),(370,),'<i8',100)
   npy(self.root/'2b-f0nsf'/(name+'.npy'),(370,),'<f4',150)
  report=prep.audit_preprocessed(self.root,expected_sources=1,validate_features=True)
  self.assertEqual(report['status'],'insufficient-effective-data')
  self.assertEqual(report['activeLowerBoundSeconds'],0)
 def test_missing_middle_output_chunk_is_rejected(self):
  self.pair('0_0.wav');self.pair('0_2.wav')
  with self.assertRaisesRegex(ValueError,'sequence'):prep.audit_preprocessed(self.root,expected_sources=1)

 def test_even_excluded_chunks_require_valid_feature_outputs(self):
  self.pair('0_0.wav',seconds=.5)
  with self.assertRaisesRegex(ValueError,'output'):prep.audit_preprocessed(self.root,expected_sources=1,validate_features=True)


class ArrayTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve()
 def paths(self):return [self.root/'feature.npy',self.root/'f0.npy',self.root/'f0nsf.npy']
 def valid(self):
  feature,f0,nsf=self.paths();npy(feature,(10,768));npy(f0,(20,),'<i8',100);npy(nsf,(20,),'<f8',150)
 def test_valid_arrays_accepted(self):
  self.valid();prep.validate_arrays(*self.paths())
 def test_nonfinite_features_rejected(self):
  self.valid();npy(self.paths()[0],(10,768),value=float('nan'))
  with self.assertRaisesRegex(ValueError,'finite'):prep.validate_arrays(*self.paths())
 def test_wrong_feature_dimensions_rejected(self):
  self.valid();npy(self.paths()[0],(10,256))
  with self.assertRaises(ValueError):prep.validate_arrays(*self.paths())
 def test_truncated_array_rejected(self):
  self.valid();p=self.paths()[1];p.write_bytes(p.read_bytes()[:-1])
  with self.assertRaises(ValueError):prep.validate_arrays(*self.paths())
 def test_mismatched_pitch_lengths_rejected(self):
  self.valid();npy(self.paths()[2],(19,))
  with self.assertRaises(ValueError):prep.validate_arrays(*self.paths())


# Exact pinned public upstream fixture; guarded by the production SHA256.
UPSTREAM_SOURCE = r'''import multiprocessing
import os
import sys

from scipy import signal

inp_root = sys.argv[1]
sr = int(sys.argv[2])
n_p = int(sys.argv[3])
exp_dir = sys.argv[4]
noparallel = sys.argv[5] == "True"
per = float(sys.argv[6])
manifest_path = sys.argv[7] if len(sys.argv) > 7 else ""
import traceback

import librosa
import numpy as np
from scipy.io import wavfile

os.environ["RVC_AUDIO_FORCE_CPU"] = "1"
from infer.audio import load_audio
from train.dataset.slicer2 import Slicer
from i18n.i18n import I18nAuto
from tools.progress import should_report
from tools.multispeaker import ManifestError, load_manifest

i18n = I18nAuto()

f = open("%s/preprocess.log" % exp_dir, "a", encoding="utf8")


def println(strr):
    print(strr)
    f.write("%s\n" % strr)
    f.flush()


class PreProcess:
    def __init__(self, sr, exp_dir, per=3.7):
        self.slicer = Slicer(
            sr=sr,
            threshold=-42,
            min_length=1500,
            min_interval=400,
            hop_size=15,
            max_sil_kept=500,
        )
        self.sr = sr
        self.bh, self.ah = signal.butter(N=5, Wn=48, btype="high", fs=self.sr)
        self.per = per
        self.overlap = 0.3
        self.tail = self.per + self.overlap
        self.max = 0.9
        self.alpha = 0.75
        self.exp_dir = exp_dir
        self.gt_wavs_dir = "%s/0_gt_wavs" % exp_dir
        self.wavs16k_dir = "%s/1_16k_wavs" % exp_dir
        os.makedirs(self.exp_dir, exist_ok=True)
        os.makedirs(self.gt_wavs_dir, exist_ok=True)
        os.makedirs(self.wavs16k_dir, exist_ok=True)

    def norm_write(self, tmp_audio, output_key, idx1):
        tmp_max = np.abs(tmp_audio).max()
        if not np.isfinite(tmp_max) or tmp_max <= 0 or tmp_max > 2.5:
            println(
                i18n("[数据切分][跳过] 无效或异常音频片段：%s_%s | 峰值：%s")
                % (output_key, idx1, tmp_max)
            )
            return False
        tmp_audio = (tmp_audio / tmp_max * (self.max * self.alpha)) + (
            1 - self.alpha
        ) * tmp_audio
        wavfile.write(
            "%s/%s_%s.wav" % (self.gt_wavs_dir, output_key, idx1),
            self.sr,
            tmp_audio.astype(np.float32),
        )
        audio_16k = librosa.resample(
            tmp_audio, orig_sr=self.sr, target_sr=16000
        ).astype(np.float32)
        wavfile.write(
            "%s/%s_%s.wav" % (self.wavs16k_dir, output_key, idx1),
            16000,
            audio_16k,
        )
        return True

    def pipeline(self, path, output_key, progress_index, total):
        try:
            audio = load_audio(path, self.sr)
            # zero phased digital filter cause pre-ringing noise...
            # audio = signal.filtfilt(self.bh, self.ah, audio)
            audio = signal.lfilter(self.bh, self.ah, audio)

            idx1 = 0
            for audio in self.slicer.slice(audio):
                i = 0
                while 1:
                    start = int(self.sr * (self.per - self.overlap) * i)
                    i += 1
                    if len(audio[start:]) > self.tail * self.sr:
                        tmp_audio = audio[start : start + int(self.per * self.sr)]
                        self.norm_write(tmp_audio, output_key, idx1)
                        idx1 += 1
                    else:
                        tmp_audio = audio[start:]
                        idx1 += 1
                        break
            self.norm_write(tmp_audio, output_key, idx1)
            if should_report(progress_index, total):
                println(
                    i18n("[数据切分] 进度：%s/%s | %s")
                    % (progress_index + 1, total, os.path.basename(path))
                )
            return True
        except Exception:
            println(
                i18n("[数据切分][失败] %s\n%s")
                % (path, traceback.format_exc())
            )
            return False

    def pipeline_mp(self, infos):
        success = 0
        failed = 0
        for path, output_key, progress_index, total in infos:
            if self.pipeline(path, output_key, progress_index, total):
                success += 1
            else:
                failed += 1
        if infos:
            println(
                i18n("[数据切分] 子任务完成 | 成功：%s | 失败：%s")
                % (success, failed)
            )

    def pipeline_mp_inp_dir(self, inp_root, n_p):
        try:
            names = sorted(
                name for name in os.listdir(inp_root)
                if os.path.isfile(os.path.join(inp_root, name))
            )
            total = len(names)
            infos = [
                ("%s/%s" % (inp_root, name), str(idx), idx, total)
                for idx, name in enumerate(names)
            ]
            worker_count = max(n_p, 1)
            worker_count = min(worker_count, max(total, 1))
            println(
                i18n("[数据切分] 待处理：%s | 进程数：%s")
                % (total, worker_count)
            )
            if noparallel:
                for i in range(worker_count):
                    self.pipeline_mp(infos[i::worker_count])
            else:
                ps = []
                for i in range(worker_count):
                    p = multiprocessing.Process(
                        target=self.pipeline_mp, args=(infos[i::worker_count],)
                    )
                    ps.append(p)
                    p.start()
                for i in range(worker_count):
                    ps[i].join()
        except Exception:
            println(i18n("[数据切分][失败] %s") % traceback.format_exc())

    def pipeline_mp_manifest(self, manifest_entries, n_p):
        infos = [
            (entry["path"], entry["output_key"], idx, len(manifest_entries))
            for idx, entry in enumerate(manifest_entries)
        ]
        total = len(infos)
        worker_count = max(n_p, 1)
        worker_count = min(worker_count, max(total, 1))
        println(
            i18n("[数据切分] 多说话人待处理：%s | 进程数：%s")
            % (total, worker_count)
        )
        if noparallel:
            for i in range(worker_count):
                self.pipeline_mp(infos[i::worker_count])
            return
        ps = []
        for i in range(worker_count):
            p = multiprocessing.Process(
                target=self.pipeline_mp, args=(infos[i::worker_count],)
            )
            ps.append(p)
            p.start()
        for p in ps:
            p.join()


def preprocess_trainset(inp_root, sr, n_p, exp_dir, per):
    pp = PreProcess(sr, exp_dir, per)
    println(i18n("[数据切分] 开始"))
    if manifest_path:
        try:
            manifest = load_manifest(exp_dir)
            for output_dir in (pp.gt_wavs_dir, pp.wavs16k_dir):
                for name in os.listdir(output_dir):
                    if name.startswith("ms") and name.endswith(".wav"):
                        try:
                            os.remove(os.path.join(output_dir, name))
                        except OSError:
                            pass
            pp.pipeline_mp_manifest(manifest["entries"], n_p)
        except ManifestError as error:
            println(i18n(error.key) % error.values)
            raise
    else:
        for output_dir in (pp.gt_wavs_dir, pp.wavs16k_dir):
            for name in os.listdir(output_dir):
                if name.startswith("ms") and name.endswith(".wav"):
                    try:
                        os.remove(os.path.join(output_dir, name))
                    except OSError:
                        pass
        pp.pipeline_mp_inp_dir(inp_root, n_p)
    println(i18n("[数据切分] 完成"))


if __name__ == "__main__":
    preprocess_trainset(inp_root, sr, n_p, exp_dir, per)
'''


class TailRepairTests(unittest.TestCase):
 def run_slices(self,lengths):
  import ast
  from types import SimpleNamespace
  tree,provenance=prep.build_preprocess(UPSTREAM_SOURCE.encode())
  original=ast.parse(UPSTREAM_SOURCE)
  klass=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='PreProcess')
  namespace=dict(signal=SimpleNamespace(lfilter=lambda b,a,x:x),load_audio=lambda path,sr:[],should_report=lambda *args:False)
  exec(compile(ast.Module(body=[klass],type_ignores=[]),'fixture','exec'),namespace)
  processor=namespace['PreProcess'].__new__(namespace['PreProcess'])
  processor.sr=10;processor.per=3.7;processor.overlap=.3;processor.tail=4;processor.bh=processor.ah=[]
  processor.slicer=SimpleNamespace(slice=lambda audio:[list(range(length)) for length in lengths])
  writes=[];processor.norm_write=lambda audio,key,index:writes.append((index,len(audio)))
  self.assertTrue(processor.pipeline('input','0',0,1))
  return writes,provenance
 def test_every_short_slice_tail_is_retained(self):
  writes,_=self.run_slices([20,15,30]);self.assertEqual(writes,[(0,20),(1,15),(2,30)])
 def test_short_tail_then_long_slice_has_unique_sequential_names(self):
  writes,_=self.run_slices([20,80]);self.assertEqual(writes,[(0,20),(1,37),(2,37),(3,12)])
 def test_different_upstream_source_is_rejected(self):
  with self.assertRaisesRegex(ValueError,'source hash'):prep.build_preprocess((UPSTREAM_SOURCE+'# changed\n').encode())
 def test_crlf_source_is_normalized_but_raw_hash_recorded(self):
  _,normal=prep.build_preprocess(UPSTREAM_SOURCE.encode())
  _,windows=prep.build_preprocess(UPSTREAM_SOURCE.replace('\n','\r\n').encode())
  self.assertEqual(normal['normalizedSourceSHA256'],windows['normalizedSourceSHA256'])
  self.assertNotEqual(normal['rawSourceSHA256'],windows['rawSourceSHA256'])
