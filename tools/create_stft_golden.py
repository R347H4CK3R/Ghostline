"""Independent NumPy fixtures for the native OpenVoice linear STFT frontend."""
import json,numpy as np
from pathlib import Path
n=4096; t=np.arange(n,dtype=np.float64);window=(0.5-0.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32)
cases=[]
for name in ['constant','nyquist','dualTone']:
 if name=='constant': wave=np.full(n,0.25,dtype=np.float32)
 elif name=='nyquist': wave=np.where(t%2==0,0.25,-0.25).astype(np.float32)
 else: wave=(0.2*np.sin(2*np.pi*440*t/22050)+0.1*np.sin(2*np.pi*1100*t/22050)).astype(np.float32)
 padded=np.pad(wave,(384,384),mode='reflect');points=[]
 for frame in [0,1,7,15]:
  fft=np.fft.rfft(padded[frame*256:frame*256+1024]*window)
  mags=np.sqrt(fft.real**2+fft.imag**2+1e-6)
  for b in [0,1,2,10,20,32,64,128,256,511,512]: points.append({'frame':frame,'bin':b,'magnitude':float(mags[b])})
 cases.append({'name':name,'points':points})
Path('VoiceMatrixTests/stft-golden.json').write_text(json.dumps({'sampleCount':n,'sampleRate':22050,'fftSize':1024,'hop':256,'pad':384,'cases':cases},indent=2)+'\n')
