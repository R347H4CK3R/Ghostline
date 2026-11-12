"""Bounded subprocess bridge to a separate verified CPU speaker runtime."""
import json,pathlib,tempfile
from tools.process_control import checked_process


def analyzer(python,checkpoint,vad_checkpoint,*,script=None):
 script=pathlib.Path(script or pathlib.Path(__file__).with_name('speaker_candidates.py')).resolve()
 def analyze(audio,cancelled=lambda:False):
  if cancelled():raise InterruptedError('Speaker analysis paused')
  with tempfile.TemporaryDirectory(prefix='voicematrix-speaker-result-') as directory:
   output=pathlib.Path(directory)/'result.json'
   checked_process([str(python),str(script),'--audio',str(audio),'--checkpoint',str(checkpoint),'--vad-checkpoint',str(vad_checkpoint),'--output',str(output)],timeout=600,cancelled=cancelled)
   if cancelled():raise InterruptedError('Speaker analysis paused')
   if output.is_symlink() or not output.is_file() or output.stat().st_size>131072:raise ValueError('Speaker analysis response is missing or exceeds its bound')
   result=json.loads(output.read_text(encoding='utf8'))
   if not isinstance(result,dict):raise ValueError('Invalid speaker-analysis response')
   return result
 return analyze
