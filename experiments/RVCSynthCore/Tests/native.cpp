#include "RVCSynthCore.h"
#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>
#include <limits>
#include <vector>
#include <string>
std::vector<char> read(const std::string& p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char**argv){
 assert(argc==2);std::string root=argv[1]; RVCSynthSession* s=nullptr;
 auto model=read(root+"/valid.onnx");assert(!model.empty());
 assert(rvc_synth_create(model.data(),model.size(),&s)==RVC_OK && s);
 std::vector<float> phone(76800,.1f),pitchf(100,220),latent(19200,.1f),phase(1,.2f),noise(40000,.25f),out(40000,999);
 std::vector<int64_t> lengths{100},pitch(100,100),speaker{0};
 int64_t a[]={1,100,768},b[]={1},c[]={1,100},d[]={1,192,100},e[]={1,1,1},f[]={1,40000,1};
 RVCTensor in[]={
 {"phone",RVC_FLOAT32,a,3,phone.data(),phone.size()*4},{"lengths",RVC_INT64,b,1,lengths.data(),8},
 {"pitch",RVC_INT64,c,2,pitch.data(),800},{"pitchf",RVC_FLOAT32,c,2,pitchf.data(),400},
 {"speaker",RVC_INT64,b,1,speaker.data(),8},{"latent_noise",RVC_FLOAT32,d,3,latent.data(),latent.size()*4},
 {"phase_noise",RVC_FLOAT32,e,3,phase.data(),4},{"excitation_noise",RVC_FLOAT32,f,3,noise.data(),noise.size()*4}};
 RVCCancel* cancel=rvc_cancel_create();assert(cancel);
 assert(rvc_synth_run(s,in,8,out.data(),out.size(),cancel,1000)==RVC_OK);
 for(float v:out)assert(v==.125f);
 auto check=[&](RVCStatus wanted){assert(rvc_synth_run(s,in,8,out.data(),out.size(),cancel,1000)==wanted);};
 in[0].bytes--;check(RVC_INVALID_TENSOR);in[0].bytes++;
 a[1]=101;check(RVC_INVALID_TENSOR);a[1]=100;
 in[0].name="pitch";check(RVC_INVALID_TENSOR);in[0].name="phone";
 phone[0]=std::numeric_limits<float>::quiet_NaN();check(RVC_INVALID_TENSOR);phone[0]=.1f;
 speaker[0]=1;check(RVC_INVALID_TENSOR);speaker[0]=0;
 lengths[0]=101;check(RVC_INVALID_TENSOR);lengths[0]=100;
 pitch[0]=0;check(RVC_INVALID_TENSOR);pitch[0]=256;check(RVC_INVALID_TENSOR);pitch[0]=100;
 pitchf[0]=-1;check(RVC_INVALID_TENSOR);pitchf[0]=220;
 assert(rvc_synth_run(s,in,7,out.data(),out.size(),cancel,1000)==RVC_INVALID_TENSOR);
 assert(rvc_synth_run(s,in,8,out.data(),39999,cancel,1000)==RVC_INVALID_TENSOR);
 assert(rvc_synth_run(s,in,8,out.data(),out.size(),cancel,0)==RVC_INVALID_ARGUMENT);
 rvc_cancel_request(cancel);check(RVC_CANCELLED);rvc_cancel_destroy(cancel);rvc_synth_destroy(s);
 for(auto name:{"wrong_input","dynamic_input","missing_input","extra_input","wrong_output"}){
  auto bad=read(root+"/"+name+".onnx");s=nullptr;assert(rvc_synth_create(bad.data(),bad.size(),&s)==RVC_INVALID_MODEL && !s);
 }
 auto nan=read(root+"/nan_output.onnx");assert(rvc_synth_create(nan.data(),nan.size(),&s)==RVC_OK);
 cancel=rvc_cancel_create();std::fill(out.begin(),out.end(),999);
 assert(rvc_synth_run(s,in,8,out.data(),out.size(),cancel,1000)==RVC_INVALID_OUTPUT);
 for(float v:out)assert(v==999); // output publication is transactional
 rvc_cancel_destroy(cancel);rvc_synth_destroy(s);
 s=nullptr;assert(rvc_synth_create(model.data(),128*1024*1024+1,&s)==RVC_INVALID_ARGUMENT);
 assert(rvc_synth_create("bad",3,&s)==RVC_INVALID_MODEL && !s);
 std::cout<<"Native ORT synthesis contract: all assertions passed\n";
}
