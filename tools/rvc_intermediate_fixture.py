"""Private one-second synthetic RVC intermediate capture; not a portable runtime.

No downloads, installation, catalog changes or iPhone support. Expensive work runs
only in a separate bounded child. All capture wrappers restore originals finally.
New POSIX capture folders are owner-only. On Windows the authorized parent ACL
is inherited and must be validated before a real run. request.json contains a
private local source path: keep it and capture.log private, not public evidence.
"""
import argparse
import array
import contextlib
import json
import importlib.metadata
import hashlib
import math
import os
import pathlib
import re
import socket
import subprocess
import sys
import wave

if __package__ in (None, ''):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tools.rvc_export import read_bound, sha, audio_metrics, MAX_MODEL_BYTES, MAX_INDEX_BYTES, MAX_AUDIO_BYTES, UPSTREAM
from tools.rvc_portable import _checked_proof, _path, _capture_random
from tools.rvc_training import run_stage
from tools.rvc_validation import check_source, _write

# Actual upstream reference gets one-second left/right reflect context, hence
# 48,000 encoder samples and up to 300 synthesizer frames, NOT the old 100 shape.
SPEC = {
 'audio_16k': ('float32', 1, 16000), 'padded_audio': ('float64', 1, 48000), 'filtered_audio': ('float64', 1, 16000),
 'hubert_input': ('float32', 2, 48000), 'hubert_features': ('float32', 3, 150*768),
 'retrieval_scores': ('float32', 2, 150*8), 'retrieval_ids': ('int64', 2, 150*8),
 'retrieval_vectors': ('float32', 3, 150*8*768),
 'pitch_coarse': ('int64', 2, 300), 'pitch_hz': ('float32', 2, 300),
 'synth_features': ('float32', 3, 300*768), 'synth_lengths': ('int64', 1, 1),
 'speaker': ('int64', 1, 1), 'latent_noise': ('float32', 3, 192*300),
 'phase_noise': ('float32', 3, 1), 'excitation_noise': ('float32', 3, 120000),
 'synth_output': ('float32', 3, 120000), 'final_pcm': ('int16', 1, 40000),
}
CODES = {'float64': ('d', 8), 'float32': ('f', 4), 'int64': ('q', 8), 'int16': ('h', 2)}


class Capture:
    def __init__(self, folder):
        self.folder = _path(folder); self.entries = {}

    @staticmethod
    def validate_tensor(name, raw, shape, dtype):
        if name not in SPEC:
            raise ValueError('Unknown capture stage')
        expected, rank, maximum = SPEC[name]
        if (dtype != expected or not isinstance(shape, list) or len(shape) != rank or
                any(type(x) is not int or x < 1 for x in shape) or math.prod(shape) > maximum or
                len(raw) != math.prod(shape)*CODES[dtype][1]):
            raise ValueError('Invalid bounded stage shape or dtype')
        if name in ('hubert_features', 'synth_features') and (shape[0] != 1 or shape[-1] != 768):
            raise ValueError('Expected batch-one 768-dimensional features')
        if name.startswith('retrieval_') and (shape[1] != 8 or (name == 'retrieval_vectors' and shape[-1] != 768)):
            raise ValueError('Expected eight retrieval neighbors')
        if name == 'hubert_input' and shape[0] != 1:
            raise ValueError('Expected one encoder input')
        values = array.array(CODES[dtype][0], raw)
        if sys.byteorder != 'little': values.byteswap()
        if any(not math.isfinite(x) for x in values): raise ValueError('Nonfinite stage values')
        if name == 'retrieval_scores' and any(x <= 0 for x in values):
            raise ValueError('Degenerate retrieval distances cannot produce reference weights')
        if name == 'retrieval_ids' and any(x < 0 for x in values): raise ValueError('Missing retrieval neighbor')

    def add(self, name, raw, shape, dtype):
        if name in self.entries: raise ValueError('Repeated capture stage')
        self.validate_tensor(name, raw, shape, dtype)
        path = self.folder / (name + '.bin')
        with path.open('xb') as f: f.write(raw)
        self.entries[name] = dict(file=path.name, sha256=sha(raw), bytes=len(raw), dtype=dtype, shape=shape)

    def tensor(self, name, value, dtype=None):
        import numpy as np
        if hasattr(value, 'detach'): value = value.detach().cpu().numpy()
        dtype = dtype or SPEC[name][0]
        # Explicit canonical conversion, never a change to the live inference value.
        value = np.asarray(value, dtype={'float64':'<f8','float32':'<f4','int64':'<i8','int16':'<i2'}[dtype], order='C')
        self.add(name, value.tobytes(), list(value.shape), dtype)

    def verify(self):
        for name, meta in self.entries.items():
            if (name not in SPEC or not isinstance(meta, dict) or
                    set(meta) != {'file','sha256','bytes','dtype','shape'} or
                    meta.get('file') != name + '.bin' or type(meta.get('bytes')) is not int or
                    not isinstance(meta.get('sha256'),str) or not re.fullmatch('[0-9a-f]{64}',meta['sha256'])):
                raise ValueError('Invalid stage metadata')
            raw = read_bound(_path(self.folder / meta['file']), 8*1024*1024, meta['sha256'])
            if len(raw) != meta['bytes']: raise ValueError('Changed stage size')
            self.validate_tensor(name,raw,meta['shape'],meta['dtype'])

    def complete(self):
        if set(self.entries) != set(SPEC): raise ValueError('Not every reference stage was captured')
        self.verify()
        e = self.entries
        rows = e['hubert_features']['shape'][1]
        if any(e[n]['shape'][0] != rows for n in ('retrieval_scores','retrieval_ids','retrieval_vectors')):
            raise ValueError('Retrieval row mismatch')
        frames = e['synth_features']['shape'][1]
        if (frames != rows*2 or e['latent_noise']['shape'] != [1,192,frames] or
                any(e[n]['shape'] != [1,frames] for n in ('pitch_coarse','pitch_hz')) or
                e['synth_output']['shape'] != [1,1,frames*400] or
                e['excitation_noise']['shape'] != [1,frames*400,1] or
                e['phase_noise']['shape'] != [1,1,1] or
                e['final_pcm']['shape'] != [frames*400-80000] or
                e['audio_16k']['shape'] != [16000] or e['filtered_audio']['shape'] != [16000] or e['padded_audio']['shape'] != [48000]):
            raise ValueError('Reference frame, context or trimming contract changed')
        lengths=array.array('q',read_bound(self.folder/'synth_lengths.bin',8))
        speaker=array.array('q',read_bound(self.folder/'speaker.bin',8))
        if sys.byteorder != 'little': lengths.byteswap(); speaker.byteswap()
        if list(lengths) != [frames] or list(speaker) != [0]:
            raise ValueError('Unexpected frame count or speaker value')
        self.verify()
        return dict(self.entries)


def check_signature(function, required, optional=()):
    import inspect
    parameters=list(inspect.signature(function).parameters.values())
    if tuple(p.name for p in parameters) != tuple(required)+tuple(optional):
        raise ValueError('Pinned upstream wrapper signature changed')
    for index,p in enumerate(parameters):
        expected=inspect.Parameter.empty if index<len(required) else None
        if p.kind != inspect.Parameter.POSITIONAL_OR_KEYWORD or p.default is not expected:
            raise ValueError('Pinned upstream wrapper defaults changed')


def _hubert_assets(root):
    directory = _path(pathlib.Path(root)/'assets'/'hubert_base')
    files = sorted(p for p in directory.iterdir() if p.name in ('config.json','preprocessor_config.json') or p.suffix in ('.bin','.safetensors'))
    if (not {'config.json','preprocessor_config.json'}.issubset({p.name for p in files}) or
            not any(p.suffix in ('.bin','.safetensors') for p in files) or len(files)>8):
        raise ValueError('Incomplete local encoder asset contract')
    result={}; total=0
    for p in files:
        p=_path(p); size=p.stat().st_size; total+=size
        if not p.is_file() or not 0<size<=512*1024*1024 or total>768*1024*1024:
            raise ValueError('Encoder assets exceed capture budget')
        h=hashlib.sha256(); consumed=0
        with p.open('rb') as f:
            while block:=f.read(1024*1024):
                consumed+=len(block)
                if consumed>size:raise ValueError('Encoder asset grew')
                h.update(block)
        if consumed!=size:raise ValueError('Encoder asset changed')
        result[p.name]=dict(bytes=size,sha256=h.hexdigest())
    return result


@contextlib.contextmanager
def _replace(obj, name, replacement):
    original = getattr(obj, name); setattr(obj, name, replacement)
    try: yield original
    finally: setattr(obj, name, original)


def capture(root, proof_path, source_path, folder, *, proof_sha256, source_sha256,
            synthetic, python=sys.executable, timeout=600, cancel=None):
    if synthetic is not True: raise ValueError('Explicit original synthetic fixture declaration required')
    if any(not isinstance(x,str) or not re.fullmatch('[0-9a-f]{64}',x) for x in (proof_sha256,source_sha256)):
        raise ValueError('Explicit SHA-256 proof and source bindings are required')
    if type(timeout) not in (int,float) or not 0 < timeout <= 1800: raise ValueError('Invalid timeout')
    root, folder = _path(root), _path(folder)
    if root == folder or root in folder.parents or any((p/'collection.json').exists() for p in (folder,*folder.parents)):
        raise ValueError('Keep private captures outside source and F5 collections')
    if cancel and cancel.is_set(): raise InterruptedError('Cancelled')
    proof_bytes = read_bound(_path(proof_path), 1024*1024, proof_sha256)
    proof = _checked_proof(proof_bytes)
    if proof.get('inputSHA256') != source_sha256: raise ValueError('Source is not bound to the checked synthetic conversion')
    source = read_bound(_path(source_path), MAX_AUDIO_BYTES, source_sha256)
    if audio_metrics(source)['seconds'] < 1: raise ValueError('Need at least one second of held-out synthetic speech')
    model = read_bound(_path(proof['model']), MAX_MODEL_BYTES, proof['modelSHA256'])
    index = read_bound(_path(proof['index']), MAX_INDEX_BYTES, proof['indexSHA256'])
    folder.mkdir(mode=0o700, exist_ok=False)
    state = dict(schemaVersion=1,status='checking',sourceRevision=UPSTREAM,
                 syntheticFixture=True,sourceSHA256=source_sha256,proofSHA256=proof_sha256,
                 modelSHA256=proof['modelSHA256'],indexSHA256=proof['indexSHA256'],
                 nativeIPhoneRuntimeVerified=False,portablePipelineVerified=False)
    _write(folder/'fixture.json',state)
    try:
        for name, data in [('model.pth',model),('model.index',index),('input.wav',source)]:
            (folder/name).write_bytes(data)
        request = dict(root=str(root),bindings={n:sha((folder/n).read_bytes()) for n in ('model.pth','model.index','input.wav')})
        _write(folder/'request.json',request)
        env = dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='',RVC_CUDA_GRAPH='0',OMP_NUM_THREADS='2')
        env.pop('PYTHONPATH',None)
        with (folder/'capture.log').open('wb') as log:
            run_stage([str(python),'-I',str(pathlib.Path(__file__).resolve()),'--child',str(folder/'request.json'),sha((folder/'request.json').read_bytes())],cwd=folder,env=env,log=log,timeout=timeout,cancel=cancel)
        if cancel and cancel.is_set(): raise InterruptedError('Cancelled')
        result=json.loads(read_bound(folder/'child-result.json',1024*1024))
        if result.get('bindings') != request['bindings']: raise ValueError('Child binding mismatch')
        verify=Capture(folder); verify.entries=result['stages']; verify.complete()
        if result.get('hubertAssets') != _hubert_assets(root):raise ValueError('Encoder asset binding changed')
        with wave.open(str(folder/'converted.wav'),'rb') as audio:
            if (audio.getnchannels(),audio.getsampwidth(),audio.getframerate()) != (1,2,40000) or audio.readframes(audio.getnframes()) != (folder/'final_pcm.bin').read_bytes():
                raise ValueError('Final PCM differs from the actual conversion')
        for name,digest in request['bindings'].items():read_bound(_path(folder/name),MAX_MODEL_BYTES,digest)
        state.update(status='desktop-reference-captured',stages=result['stages'],contract=result['contract'],hubertAssets=result['hubertAssets'],versions=result['versions'])
        _write(folder/'fixture.json',state)
    except BaseException as error:
        # Do not serialize exception text: third-party errors may contain paths or user data.
        state.update(status='cancelled' if isinstance(error,(InterruptedError,KeyboardInterrupt)) else 'failed',errorType=type(error).__name__)
        _write(folder/'fixture.json',state); raise
    return folder/'fixture.json'


def _child(request_path, digest):
    sys.dont_write_bytecode=True
    def offline(*args,**kwargs): raise RuntimeError('Network disabled for reference capture')
    socket.socket.connect=offline; socket.socket.connect_ex=offline; socket.create_connection=offline
    path=_path(request_path); folder=path.parent
    request=json.loads(read_bound(path,65536,digest)); root=_path(request['root'])
    check_source(root)
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--','infer','tools'],cwd=root,text=True,timeout=10).strip():
        raise ValueError('Untracked or changed inference source')
    for name,digest in request['bindings'].items():read_bound(_path(folder/name),MAX_MODEL_BYTES,digest)
    import fractions
    import io
    import numpy as np
    import scipy.signal
    import soundfile as sf
    import torch
    import faiss
    sys.path.insert(0,str(root))
    import tools
    if str(root/'tools') not in tools.__path__:tools.__path__.append(str(root/'tools'))
    from infer.vc import pipeline as upstream
    from infer.module.models import SynthesizerTrnMs768NSFsid
    from tools.rvc_validation import _child as conversion
    writer=Capture(folder)
    hubert_assets=_hubert_assets(root)
    audio,rate=sf.read(io.BytesIO(read_bound(folder/'input.wav',MAX_AUDIO_BYTES)),dtype='float32')
    ratio=fractions.Fraction(16000,rate)
    audio=scipy.signal.resample_poly(audio,ratio.numerator,ratio.denominator)[:16000]
    if len(audio)!=16000:raise ValueError('Short fixture')
    # FLOAT WAV avoids a new PCM16 quantization; conversion's audio checker expects
    # PCM16, therefore use an explicit PCM16 fixture and record its decoded samples.
    sf.write(folder/'one-second.wav',audio,16000,subtype='PCM_16')
    decoded, _ = sf.read(folder/'one-second.wav',dtype='float32')
    writer.tensor('audio_16k',decoded)
    # Capture reflects the exact post-quantization input actually given to pipeline.
    # Keep the resampled original distinct in contract; do not claim byte identity.
    original_extract=upstream.extract_hubert_features
    check_signature(original_extract,('model','source','version'),('padding_mask',))
    check_signature(upstream.Pipeline.get_f0,('self','x','p_len','f0_up_key','f0_method'))
    check_signature(SynthesizerTrnMs768NSFsid.infer,('self','phone','phone_lengths','pitch','nsff0','sid'),('skip_head','return_length','return_length2'))
    def extract(model,source,version,padding_mask=None):
        writer.tensor('hubert_input',source)
        result=original_extract(model,source,version,padding_mask=padding_mask)
        writer.tensor('hubert_features',result); return result
    original_f0=upstream.Pipeline.get_f0
    def f0(self,x,p_len,key,method):
        writer.tensor('padded_audio',x)
        writer.tensor('filtered_audio',x[self.t_pad:-self.t_pad])
        return original_f0(self,x,p_len,key,method)
    original_read=faiss.read_index
    class Index:
        def __init__(self,base):self.base=base
        def __getattr__(self,name):return getattr(self.base,name)
        def reconstruct_n(self,*args):self.vectors=self.base.reconstruct_n(*args);return self.vectors
        def search(self,query,k):
            scores,ids=self.base.search(query,k)
            writer.tensor('retrieval_scores',scores);writer.tensor('retrieval_ids',ids)
            if (ids<0).any():raise ValueError('Insufficient neighbors')
            writer.tensor('retrieval_vectors',self.vectors[ids]);return scores,ids
    original_infer=SynthesizerTrnMs768NSFsid.infer
    def infer(self,*args,**kwargs):
        if kwargs or len(args)!=5:raise ValueError('Unexpected synth call')
        for name,value in zip(('synth_features','synth_lengths','pitch_coarse','pitch_hz','speaker'),args):writer.tensor(name,value)
        with _capture_random(torch) as draws:result=original_infer(self,*args)
        if [kind for kind,_ in draws]!=['normal','uniform','normal']:raise ValueError('Noise contract changed')
        for name,(_,value) in zip(('latent_noise','phase_noise','excitation_noise'),draws):writer.tensor(name,value)
        writer.tensor('synth_output',result[0]);return result
    with _replace(upstream,'extract_hubert_features',extract), _replace(upstream.Pipeline,'get_f0',f0), _replace(faiss,'read_index',lambda p:Index(original_read(p))), _replace(SynthesizerTrnMs768NSFsid,'infer',infer):
        conversion(root,folder/'model.pth',folder/'model.index',folder/'one-second.wav',folder/'converted.wav',folder/'conversion-boundary.json')
    final,rate=sf.read(folder/'converted.wav',dtype='int16')
    if rate!=40000:raise ValueError('Output sample rate changed')
    writer.tensor('final_pcm',final)
    check_source(root)
    if _hubert_assets(root)!=hubert_assets:raise ValueError('Encoder asset mutation')
    stages=writer.complete()
    contract=dict(inputSeconds=1,resample='scipy.signal.resample_poly then PCM16',contextSecondsEachSide=1,hubertVersion='v2-final-layer-12',pitchMethod='pm',indexRate=.75,neighbors=8,protect=.33,rmsMixRate=1,outputRate=40000)
    versions={name:importlib.metadata.version(name) for name in ('torch','numpy','scipy','transformers','praat-parselmouth','faiss-cpu','soundfile')}
    _write(folder/'child-result.json',dict(bindings=request['bindings'],stages=stages,contract=contract,hubertAssets=hubert_assets,versions=versions))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child',nargs=2,required=True)
    args=parser.parse_args();_child(*args.child)
