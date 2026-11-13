#include "pitch.h"
#include <array>
#include <cmath>
#include <cstdint>
#include <algorithm>
#include <cstring>
namespace {
bool overlap(const void* a,size_t an,const void* b,size_t bn){
 auto x=reinterpret_cast<uintptr_t>(a),y=reinterpret_cast<uintptr_t>(b);
 return x>UINTPTR_MAX-an||y>UINTPTR_MAX-bn||(x<y+bn&&y<x+an);
}
constexpr double offset=1997.3794084376191;
double hz(double bin){return 10*std::pow(2.,(20*bin+offset)/1200);}
}
extern "C" int rvc_pitch_frames(const float* audio,size_t samples,size_t first,size_t count,float* output,float* rms){
 if(!audio||!output||!rms||samples==0||samples>48000||count==0||count>16||first>samples/160||count>1+samples/160-first||overlap(output,count*1024*4,rms,count*4))return 0;
 for(size_t i=0;i<samples;++i)if(!std::isfinite(audio[i])||std::abs(audio[i])>1)return 0;
 std::array<float,16*1024> framed{};std::array<float,16> energy{};
 for(size_t f=0;f<count;++f){
  double mean=0;for(size_t j=0;j<1024;++j){
   int64_t index=static_cast<int64_t>((first+f)*160+j)-512;float x=index>=0&&index<static_cast<int64_t>(samples)?audio[index]:0;
   framed[f*1024+j]=x;mean+=x;
  }
  mean/=1024;
  double variance=0;for(size_t j=0;j<1024;++j){double x=framed[f*1024+j]-mean;variance+=x*x;}
  energy[f]=std::sqrt(variance/1024);
  double scale=std::max(1e-10,std::sqrt(variance/1023));
  for(size_t j=0;j<1024;++j)framed[f*1024+j]=static_cast<float>((framed[f*1024+j]-mean)/scale);
 }
 std::memcpy(output,framed.data(),count*1024*4);std::memcpy(rms,energy.data(),count*4);return 1;
}
extern "C" int rvc_pitch_decode(const float* salience,size_t count,const float* energy,float minimum,float maximum,float threshold,float floor,float* pitch,float* confidence){
 if(!salience||!energy||!pitch||!confidence||count==0||count>16||!std::isfinite(minimum)||!std::isfinite(maximum)||minimum<hz(0)||maximum>hz(359)||minimum>=maximum||!std::isfinite(threshold)||threshold<0||threshold>1||!std::isfinite(floor)||floor<0||floor>1||overlap(pitch,count*4,confidence,count*4))return 0;
 for(size_t i=0;i<count*360;++i)if(!std::isfinite(salience[i])||salience[i]<0||salience[i]>1)return 0;
 for(size_t i=0;i<count;++i)if(!std::isfinite(energy[i])||energy[i]<0||energy[i]>1)return 0;
 int lo=0,hi=359;while(lo<359&&hz(lo)<minimum)++lo;while(hi>0&&hz(hi)>maximum)--hi;if(lo>hi)return 0;
 std::array<float,16> pitches{},conf{};
 for(size_t f=0;f<count;++f){
  int best=lo;for(int b=lo+1;b<=hi;++b)if(salience[f*360+b]>salience[f*360+best])best=b;
  conf[f]=salience[f*360+best];if(conf[f]<threshold||energy[f]<floor)continue;
  double sum=0,weighted=0;for(int b=std::max(lo,best-4);b<=std::min(hi,best+4);++b){double w=salience[f*360+b];sum+=w;weighted+=w*b;}
  if(sum>0)pitches[f]=static_cast<float>(hz(weighted/sum));
 }
 std::memcpy(pitch,pitches.data(),count*4);std::memcpy(confidence,conf.data(),count*4);return 1;
}
