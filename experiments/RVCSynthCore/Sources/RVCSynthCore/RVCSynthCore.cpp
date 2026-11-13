#include "RVCSynthCore.h"
#if __has_include(<onnxruntime/onnxruntime_c_api.h>)
#include <onnxruntime/onnxruntime_c_api.h>
#else
#include <onnxruntime_c_api.h>
#endif
#include <array>
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
namespace {
const OrtApi* api(){return OrtGetApiBase()->GetApi(ORT_API_VERSION);}
struct Failure { RVCStatus status; };
void checked(OrtStatus* status,RVCStatus code=RVC_RUNTIME_ERROR){
 if(status){api()->ReleaseStatus(status);throw Failure{code};}
}
struct Spec {const char* name; RVCElementType type; size_t rank; std::array<int64_t,3> shape; size_t count;};
constexpr Spec specs[]={
 {"phone",RVC_FLOAT32,3,{1,100,768},76800},{"lengths",RVC_INT64,1,{1,0,0},1},
 {"pitch",RVC_INT64,2,{1,100,0},100},{"pitchf",RVC_FLOAT32,2,{1,100,0},100},
 {"speaker",RVC_INT64,1,{1,0,0},1},{"latent_noise",RVC_FLOAT32,3,{1,192,100},19200},
 {"phase_noise",RVC_FLOAT32,3,{1,1,1},1},{"excitation_noise",RVC_FLOAT32,3,{1,40000,1},40000}};
constexpr Spec audio={"audio",RVC_FLOAT32,3,{1,1,40000},40000};
ONNXTensorElementDataType dtype(RVCElementType t){return t==RVC_FLOAT32?ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT:ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64;}
void metadata(OrtSession* session,bool input,size_t index,const Spec& spec){
 OrtAllocator* allocator=nullptr;checked(api()->GetAllocatorWithDefaultOptions(&allocator));
 char* name=nullptr;
 checked(input?api()->SessionGetInputName(session,index,allocator,&name):api()->SessionGetOutputName(session,index,allocator,&name));
 bool nameOK=name && std::strcmp(name,spec.name)==0;allocator->Free(allocator,name);
 if(!nameOK)throw Failure{RVC_INVALID_MODEL};
 OrtTypeInfo* raw=nullptr;
 checked(input?api()->SessionGetInputTypeInfo(session,index,&raw):api()->SessionGetOutputTypeInfo(session,index,&raw));
 std::unique_ptr<OrtTypeInfo,decltype(api()->ReleaseTypeInfo)> type(raw,api()->ReleaseTypeInfo);
 const OrtTensorTypeAndShapeInfo* info=nullptr;checked(api()->CastTypeInfoToTensorInfo(type.get(),&info));
 if(!info)throw Failure{RVC_INVALID_MODEL};
 ONNXTensorElementDataType element;size_t rank;
 checked(api()->GetTensorElementType(info,&element));checked(api()->GetDimensionsCount(info,&rank));
 if(rank!=spec.rank || element!=dtype(spec.type))throw Failure{RVC_INVALID_MODEL};
 std::array<int64_t,3> shape{};checked(api()->GetDimensions(info,shape.data(),rank));
 if(shape!=spec.shape)throw Failure{RVC_INVALID_MODEL};
}
void validate(const RVCTensor& t,const Spec& s){
 size_t width=s.type==RVC_FLOAT32?4:8;
 if(!t.name || std::strcmp(t.name,s.name) || t.type!=s.type || !t.shape || t.rank!=s.rank ||
    !t.data || t.bytes!=s.count*width || reinterpret_cast<uintptr_t>(t.data)%width)
  throw Failure{RVC_INVALID_TENSOR};
 for(size_t i=0;i<s.rank;++i)if(t.shape[i]!=s.shape[i])throw Failure{RVC_INVALID_TENSOR};
 if(s.type==RVC_FLOAT32){
  const float* values=static_cast<const float*>(t.data);
  for(size_t i=0;i<s.count;++i)if(!std::isfinite(values[i]))throw Failure{RVC_INVALID_TENSOR};
 }
}
}
struct RVCCancel {std::atomic<bool> requested{false};};
struct RVCSynthSession {
 OrtEnv* env=nullptr;OrtSessionOptions* options=nullptr;OrtSession* session=nullptr;OrtMemoryInfo* memory=nullptr;
 std::mutex mutex;
 size_t frames=100;
 std::array<Spec,8> inputSpecs;
 Spec outputSpec=audio;
 ~RVCSynthSession(){
  if(memory)api()->ReleaseMemoryInfo(memory);
  if(session)api()->ReleaseSession(session);
  if(options)api()->ReleaseSessionOptions(options);
  if(env)api()->ReleaseEnv(env);
 }
};
extern "C" const char* rvc_synth_runtime_version(){return OrtGetApiBase()->GetVersionString();}
extern "C" RVCStatus rvc_synth_create(const void* model,size_t bytes,RVCSynthSession** result){
 return rvc_synth_create_for_frames(model,bytes,100,result);
}
extern "C" RVCStatus rvc_synth_create_for_frames(const void* model,size_t bytes,size_t frames,RVCSynthSession** result){
 if(!result)return RVC_INVALID_ARGUMENT;
 *result=nullptr;
 if(!model || !bytes || bytes>128u*1024u*1024u || frames<1 || frames>1000)return RVC_INVALID_ARGUMENT;
 // Pin the tested API/binary boundary; no silently substituted runtime.
 if(std::strcmp(rvc_synth_runtime_version(),"1.24.2"))return RVC_RUNTIME_ERROR;
 try{
  auto s=std::make_unique<RVCSynthSession>();
  s->frames=frames;
  std::copy(std::begin(specs),std::end(specs),s->inputSpecs.begin());
  for(auto& spec:s->inputSpecs){
   spec.count=1;
   for(size_t axis=0;axis<spec.rank;++axis){
    if(spec.shape[axis]==100)spec.shape[axis]=static_cast<int64_t>(frames);
    else if(spec.shape[axis]==40000)spec.shape[axis]=static_cast<int64_t>(frames*400);
    spec.count*=static_cast<size_t>(spec.shape[axis]);
   }
  }
  s->outputSpec.shape[2]=static_cast<int64_t>(frames*400);s->outputSpec.count=frames*400;
  checked(api()->CreateEnv(ORT_LOGGING_LEVEL_FATAL,"rvc-synth",&s->env));
  checked(api()->CreateSessionOptions(&s->options));
  checked(api()->SetIntraOpNumThreads(s->options,1));checked(api()->SetInterOpNumThreads(s->options,1));
  checked(api()->SetSessionExecutionMode(s->options,ORT_SEQUENTIAL));
  checked(api()->SetSessionGraphOptimizationLevel(s->options,ORT_DISABLE_ALL));
  checked(api()->DisableCpuMemArena(s->options));checked(api()->DisableMemPattern(s->options));
  checked(api()->CreateSessionFromArray(s->env,model,bytes,s->options,&s->session),RVC_INVALID_MODEL);
  size_t inputs,outputs,initializers;
  checked(api()->SessionGetInputCount(s->session,&inputs));checked(api()->SessionGetOutputCount(s->session,&outputs));
  checked(api()->SessionGetOverridableInitializerCount(s->session,&initializers));
  if(inputs!=8 || outputs!=1 || initializers!=0)throw Failure{RVC_INVALID_MODEL};
  for(size_t i=0;i<8;++i)metadata(s->session,true,i,s->inputSpecs[i]);
  metadata(s->session,false,0,s->outputSpec);
  checked(api()->CreateCpuMemoryInfo(OrtArenaAllocator,OrtMemTypeDefault,&s->memory));
  *result=s.release();return RVC_OK;
 }catch(Failure e){return e.status;}catch(...){return RVC_RUNTIME_ERROR;}
}
extern "C" void rvc_synth_destroy(RVCSynthSession* s){delete s;}
extern "C" RVCCancel* rvc_cancel_create(){try{return new RVCCancel;}catch(...){return nullptr;}}
extern "C" void rvc_cancel_request(RVCCancel* c){if(c)c->requested.store(true);}
extern "C" void rvc_cancel_destroy(RVCCancel* c){delete c;}
extern "C" RVCStatus rvc_synth_run(RVCSynthSession* s,const RVCTensor* tensors,size_t count,
 float* output,size_t outputCount,RVCCancel* cancel,uint32_t timeout){
 if(!s || !cancel || !timeout || timeout>10000)return RVC_INVALID_ARGUMENT;
 if(!tensors || count!=8 || !output || outputCount!=s->outputSpec.count)return RVC_INVALID_TENSOR;
 std::unique_lock<std::mutex> lock(s->mutex,std::try_to_lock);if(!lock.owns_lock())return RVC_BUSY;
 if(cancel->requested.load())return RVC_CANCELLED;
 struct Values {
  OrtValue* inputs[8]={};OrtValue* output=nullptr;OrtRunOptions* run=nullptr;
  ~Values(){for(auto* v:inputs)if(v)api()->ReleaseValue(v);if(output)api()->ReleaseValue(output);if(run)api()->ReleaseRunOptions(run);}
 } values;
 try{
  for(size_t i=0;i<8;++i)validate(tensors[i],s->inputSpecs[i]);
  auto length=*static_cast<const int64_t*>(tensors[1].data);
  if(length<1 || length>static_cast<int64_t>(s->frames) || *static_cast<const int64_t*>(tensors[4].data)!=0)throw Failure{RVC_INVALID_TENSOR};
  for(size_t i=0;i<s->frames;++i){
   auto p=static_cast<const int64_t*>(tensors[2].data)[i];auto hz=static_cast<const float*>(tensors[3].data)[i];
   if(p<1 || p>255 || hz<0 || hz>20000)throw Failure{RVC_INVALID_TENSOR};
  }
  const char* names[8];
  for(size_t i=0;i<8;++i){const auto& t=tensors[i];names[i]=s->inputSpecs[i].name;
   checked(api()->CreateTensorWithDataAsOrtValue(s->memory,const_cast<void*>(t.data),t.bytes,t.shape,t.rank,dtype(t.type),&values.inputs[i]));
  }
  std::vector<float> scratch(s->outputSpec.count);
  checked(api()->CreateTensorWithDataAsOrtValue(s->memory,scratch.data(),scratch.size()*sizeof(float),s->outputSpec.shape.data(),3,ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,&values.output));
  checked(api()->CreateRunOptions(&values.run));
  std::atomic<bool> done{false};std::atomic<int> interrupted{0};
  auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(timeout);
  std::thread monitor([&]{while(!done.load()){
   int reason=cancel->requested.load()?1:(std::chrono::steady_clock::now()>=deadline?2:0);
   if(reason){interrupted.store(reason);auto* err=api()->RunOptionsSetTerminate(values.run);if(err)api()->ReleaseStatus(err);return;}
   std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }});
  const char* outputName="audio";
  auto* status=api()->Run(s->session,values.run,names,values.inputs,8,&outputName,1,&values.output);
  done.store(true);monitor.join();
  if(cancel->requested.load() || interrupted.load()){
   if(status)api()->ReleaseStatus(status);
   return cancel->requested.load() || interrupted.load()==1?RVC_CANCELLED:RVC_DEADLINE;
  }
  checked(status);
  for(float v:scratch)if(!std::isfinite(v) || std::abs(v)>1)throw Failure{RVC_INVALID_OUTPUT};
  std::memcpy(output,scratch.data(),scratch.size()*sizeof(float));return RVC_OK;
 }catch(Failure e){return e.status;}catch(...){return RVC_RUNTIME_ERROR;}
}
