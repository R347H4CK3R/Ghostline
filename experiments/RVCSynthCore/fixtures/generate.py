"""Original synthetic test graphs only, no pretrained parameters or recorded audio."""
from pathlib import Path
import onnx
from onnx import helper as h, TensorProto as T
root=Path(__file__).parent
spec=[('phone',T.FLOAT,[1,100,768]),('lengths',T.INT64,[1]),('pitch',T.INT64,[1,100]),('pitchf',T.FLOAT,[1,100]),('speaker',T.INT64,[1]),('latent_noise',T.FLOAT,[1,192,100]),('phase_noise',T.FLOAT,[1,1,1]),('excitation_noise',T.FLOAT,[1,40000,1])]
for variant in ['valid','wrong_input','dynamic_input','missing_input','extra_input','wrong_output','nan_output']:
 inputs=[h.make_tensor_value_info(n,t,s) for n,t,s in spec]
 if variant=='wrong_input':inputs[0]=h.make_tensor_value_info('phone',T.DOUBLE,[1,100,768])
 if variant=='dynamic_input':inputs[0]=h.make_tensor_value_info('phone',T.FLOAT,[1,'frames',768])
 if variant=='missing_input':inputs=inputs[1:]
 if variant=='extra_input':inputs.append(h.make_tensor_value_info('extra',T.FLOAT,[1]))
 nodes=[h.make_node('Transpose',['excitation_noise'],['transposed'],perm=[0,2,1]),h.make_node('Mul',['transposed','scale'],['audio'])]
 scale=h.make_tensor('scale',T.FLOAT,[],[float('nan') if variant=='nan_output' else .5])
 shape=[1,1,40000]
 if variant=='wrong_output':
  nodes=[h.make_node('Identity',['excitation_noise'],['audio'])];shape=[1,40000,1]
 model=h.make_model(h.make_graph(nodes,'synthetic-contract',inputs,[h.make_tensor_value_info('audio',T.FLOAT,shape)],[scale]),opset_imports=[h.make_opsetid('',17)],ir_version=9)
 onnx.checker.check_model(model);onnx.save(model,root/(variant+'.onnx'))

# Larger fixed-frame boundary, still original algebra only.
model=onnx.load(root/'valid.onnx')
for value in list(model.graph.input)+list(model.graph.output):
 for dim in value.type.tensor_type.shape.dim:
  if dim.dim_value==100:dim.dim_value=300
  elif dim.dim_value==40000:dim.dim_value=120000
onnx.checker.check_model(model)
onnx.save(model,root/'valid300.onnx')
