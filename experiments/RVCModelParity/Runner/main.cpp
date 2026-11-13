// Trusted CI artifacts only; not a production model-admission/session API.
#if __has_include(<onnxruntime/onnxruntime_c_api.h>)
#include <onnxruntime/onnxruntime_c_api.h>
#else
#include <onnxruntime_c_api.h>
#endif
#include <vector>
#include <string>
#include <fstream>
#include <iostream>
#include <cmath>
#include <stdexcept>
#include <cstring>
const OrtApi* api(){return OrtGetApiBase()->GetApi(ORT_API_VERSION);}
void check(OrtStatus* s){if(s){std::string m=api()->GetErrorMessage(s);api()->ReleaseStatus(s);throw std::runtime_error(m);}}
std::vector<float> read(const std::string& p,size_t count){
 std::ifstream f(p,std::ios::binary|std::ios::ate);
 if(!f||f.tellg()!=std::streamoff(count*4))throw std::runtime_error("Bad fixture size");
 f.seekg(0);std::vector<float> v(count);f.read(reinterpret_cast<char*>(v.data()),count*4);
 if(!f)throw std::runtime_error("Short fixture read");
 for(float x:v)if(!std::isfinite(x))throw std::runtime_error("Nonfinite fixture");return v;
}
void shape(OrtSession* s,bool input,const std::vector<int64_t>& dims){
 size_t count;check(input?api()->SessionGetInputCount(s,&count):api()->SessionGetOutputCount(s,&count));if(count!=1)throw std::runtime_error("Tensor count");
 OrtTypeInfo* info=nullptr;check(input?api()->SessionGetInputTypeInfo(s,0,&info):api()->SessionGetOutputTypeInfo(s,0,&info));
 const OrtTensorTypeAndShapeInfo* tensor=nullptr;check(api()->CastTypeInfoToTensorInfo(info,&tensor));
 size_t n;check(api()->GetDimensionsCount(tensor,&n));std::vector<int64_t> got(n);check(api()->GetDimensions(tensor,got.data(),n));
 ONNXTensorElementDataType type;check(api()->GetTensorElementType(tensor,&type));api()->ReleaseTypeInfo(info);
 if(got!=dims||type!=ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT)throw std::runtime_error("Fixed shape/type mismatch");
}
void run(const std::string& root,const std::string& name,std::vector<int64_t> inshape,std::vector<int64_t> outshape){
 OrtEnv* env=nullptr;OrtSessionOptions* options=nullptr;OrtSession* session=nullptr;OrtMemoryInfo* memory=nullptr;
 check(api()->CreateEnv(ORT_LOGGING_LEVEL_WARNING,"public-model-parity",&env));check(api()->CreateSessionOptions(&options));
 check(api()->SetIntraOpNumThreads(options,2));check(api()->SetInterOpNumThreads(options,1));check(api()->DisableCpuMemArena(options));check(api()->DisableMemPattern(options));
 check(api()->CreateSession(env,(root+"/"+name+".onnx").c_str(),options,&session));shape(session,true,inshape);shape(session,false,outshape);
 check(api()->CreateCpuMemoryInfo(OrtArenaAllocator,OrtMemTypeDefault,&memory));size_t ins=1,outs=1;for(auto x:inshape)ins*=x;for(auto x:outshape)outs*=x;
 for(int index=0;index<3;++index){
  auto prefix=root+"/"+name+"-"+std::to_string(index);auto input=read(prefix+"-input.f32",ins),expected=read(prefix+"-expected.f32",outs);
  OrtValue* in=nullptr;OrtValue* out=nullptr;check(api()->CreateTensorWithDataAsOrtValue(memory,input.data(),ins*4,inshape.data(),inshape.size(),ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,&in));
  const char* innames[]={"input"};const char* outnames[]={"output"};const OrtValue* inputs[]={in};
  check(api()->Run(session,nullptr,innames,inputs,1,outnames,1,&out));
  OrtTensorTypeAndShapeInfo* actualShape=nullptr;check(api()->GetTensorTypeAndShape(out,&actualShape));size_t actualCount=0;check(api()->GetTensorShapeElementCount(actualShape,&actualCount));api()->ReleaseTensorTypeAndShapeInfo(actualShape);
  if(actualCount!=outs)throw std::runtime_error("Output size changed");float* values=nullptr;check(api()->GetTensorMutableData(out,reinterpret_cast<void**>(&values)));
  float maxError=0;for(size_t i=0;i<outs;++i){float error=std::fabs(values[i]-expected[i]);if(!std::isfinite(values[i])||error>1e-4f+1e-3f*std::fabs(expected[i]))throw std::runtime_error("Real public model parity failed");maxError=std::max(maxError,error);}
  std::cout<<name<<" case="<<index<<" maxAbsoluteError="<<maxError<<std::endl;api()->ReleaseValue(out);api()->ReleaseValue(in);
 }
 api()->ReleaseMemoryInfo(memory);api()->ReleaseSession(session);api()->ReleaseSessionOptions(options);api()->ReleaseEnv(env);
}
int main(int argc,char** argv){try{
 if(argc!=2)throw std::runtime_error("Expected artifact directory");
 run(argv[1],"official-hubert-48000",{1,48000},{1,149,768});run(argv[1],"torchcrepe-tiny-16frames",{16,1024},{16,360});
 std::cout<<"Actual public model parity passed; not RVC voice compatibility or physical iPhone verification"<<std::endl;return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
