"""Load the measured F5 runtime using explicit local files, never hub lookups."""
import hashlib,os,pathlib

MODEL_SHA256='670900fd14e6c458b95da6e9ed317cdb20dbaf7a1c02ac06a05475a9d32b6a38'

def load_local_model(checkpoint,vocoder_directory,vocab,device='cpu',factory=None):
 checkpoint=pathlib.Path(checkpoint);vocoder=pathlib.Path(vocoder_directory);vocab=pathlib.Path(vocab)
 for path in (checkpoint,vocoder/'config.yaml',vocoder/'pytorch_model.bin',vocab):
  if not path.is_file():raise ValueError('Missing local synthesis resource: '+str(path))
 with checkpoint.open('rb') as f:
  if hashlib.file_digest(f,'sha256').hexdigest()!=MODEL_SHA256:raise ValueError('F5 checkpoint checksum mismatch')
 os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
 if factory is None:
  from f5_tts.api import F5TTS
  factory=F5TTS
 return factory(model='F5TTS_v1_Base',ckpt_file=str(checkpoint),vocoder_local_path=str(vocoder),vocab_file=str(vocab),device=device)
