"""Local model export/parity experiment; not app integration or voice likeness proof."""
import pathlib,json,hashlib,time,sys,urllib.request,os,re
from artifacts import manifest
import numpy as np
import torch
import onnxruntime as ort
from transformers import HubertModel
import torchcrepe
root=pathlib.Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
source=sys.argv[2]
if not re.fullmatch("[a-f0-9]{40}",source):raise ValueError("Invalid source SHA")
assets=root/'official-hubert';assets.mkdir(exist_ok=True)
base='https://huggingface.co/facebook/hubert-base-ls960/resolve/dba3bb02fda4248b6e082697eee756de8fe8aa8a/'
expected={'config.json':(1385,'56be398848bbd9cbc720172b0d45b2f01cac7652f2968f0f31f5faf9f2986acc'),'preprocessor_config.json':(213,'4a93853b74278b7c769d07f5a861e5d12ceb5db2bced5620d335f87238cb9e86'),'pytorch_model.bin':(377569754,'062249fffb353eab67547a2fbc129f7c31a2f459faf641b19e8fb007cc5c48ad')}
for name,(size,digest) in expected.items():
 path=assets/name
 if not path.exists():
  with urllib.request.urlopen(base+name,timeout=120) as src,path.open('wb') as out:
   total=0
   while block:=src.read(1024*1024):
    total+=len(block)
    if total>size:raise ValueError('Oversized public weight')
    out.write(block)
 with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
 if path.stat().st_size!=size or actual!=digest:raise ValueError('Public weight hash mismatch')
torch.set_num_threads(2)
torch.manual_seed(101)
class Content(torch.nn.Module):
 def __init__(self):
  super().__init__();self.net=HubertModel.from_pretrained(root/'official-hubert',local_files_only=True,attn_implementation='eager').eval()
 def forward(self,x):return self.net(x).last_hidden_state

files=[]
licenses={
 'hubert-model-card.txt':('https://huggingface.co/facebook/hubert-base-ls960/raw/dba3bb02fda4248b6e082697eee756de8fe8aa8a/README.md','c59fb00d253ab5ae5d288f130c64dddf3b7af3d5ce35c96395ac7a3db5db88f5'),
 'torchcrepe-MIT.txt':('https://raw.githubusercontent.com/maxrmorrison/torchcrepe/19e2ec3d494c0797a5ff2a11408ec5838fba6681/LICENSE','2e1d0b22e64e0f0937cb213dbe45b0b02c97d278c4db8bae926ae031325b2417'),
 'APACHE-2.0.txt':('https://www.apache.org/licenses/LICENSE-2.0.txt','cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30')}
for name,(url,digest) in licenses.items():
 with urllib.request.urlopen(url,timeout=30) as src:raw=src.read(65537)
 if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('License bytes changed')
 (root/name).write_bytes(raw);files.append(name)

report={'source':source,'hubertRevision':'dba3bb02fda4248b6e082697eee756de8fe8aa8a','pitchPackage':'torchcrepe0.0.24','kind':'real public pretrained model ONNX export and numerical parity','physicalIPhoneVerified':False,'rvcVoiceCompatibilityVerified':False,'models':[]}
def sha(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(name,model,inputs):
 model.eval();path=root/(name+'.onnx')
 torch.onnx.export(model,inputs[0],str(path),input_names=['input'],output_names=['output'],opset_version=17,dynamo=False)
 options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1;options.enable_cpu_mem_arena=False;options.enable_mem_pattern=False
 session=ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
 rows=[]
 for index,x in enumerate(inputs):
  with torch.inference_mode():a=model(x).numpy()
  t=time.monotonic();b=session.run(None,{'input':x.numpy()})[0];elapsed=time.monotonic()-t
  err=float(np.max(np.abs(a-b)));assert a.shape==b.shape and np.all(np.isfinite(b)) and np.allclose(a,b,atol=1e-4,rtol=1e-3),(name,err)
  for suffix,data in [('input',x.numpy()),('expected',a)]:
   filename=f'{name}-{index}-{suffix}.f32';data.astype('<f4').tofile(root/filename);files.append(filename)
  rows.append(dict(shape=list(b.shape),maxAbsoluteError=err,onnxSeconds=elapsed))
 files.append(path.name)
 entry=dict(name=name,sha256=sha(path),bytes=path.stat().st_size,cases=rows)
 report['models'].append(entry);(root/'export-report.json').write_text(json.dumps(report,indent=2));print(entry,flush=True)

n=48000;t=torch.arange(n)/16000
check('official-hubert-48000',Content(),[torch.zeros(1,n),(.2*torch.sin(2*torch.pi*220*t)).reshape(1,n),torch.randn(1,n)*.1])
model=torchcrepe.Crepe('tiny').eval()
weights=pathlib.Path(torchcrepe.__file__).parent/'assets'/'tiny.pth'
assert sha(weights)=='d4993eea36ed1a0ad9ac549c740dae5265b049ce72004f00c2f59e01c0be8432'
model.load_state_dict(torch.load(weights,map_location='cpu',weights_only=True))
report['pitchSourceWeightsSHA256']=sha(weights)
t=torch.arange(1024)/16000
check('torchcrepe-tiny-16frames',model,[torch.zeros(16,1024),(.2*torch.sin(2*torch.pi*220*t)).repeat(16,1),torch.randn(16,1024)])

files.append("export-report.json")
(root/"manifest.json").write_text(json.dumps(manifest(root,files,source),indent=2))
