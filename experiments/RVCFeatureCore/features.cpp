#include "features.h"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <vector>
#include <limits>

extern "C" int rvc_prepare_features(const float *original,const float *retrieved,
 size_t source_frames,size_t channels,const float *pitch_hz,size_t output_frames,
 float protect,float *output,int64_t *coarse) {
 if(!original||!retrieved||!pitch_hz||!output||!coarse||source_frames==0||source_frames>500||
    channels==0||channels>768||output_frames!=source_frames*2||!std::isfinite(protect)||protect<0||protect>1) return 0;
 const size_t n=output_frames*channels;
 const uintptr_t a=reinterpret_cast<uintptr_t>(output),b=reinterpret_cast<uintptr_t>(coarse);
 if(a>UINTPTR_MAX-n*sizeof(float)||b>UINTPTR_MAX-output_frames*sizeof(int64_t)||
    (a<b+output_frames*sizeof(int64_t)&&b<a+n*sizeof(float))) return 0;
 for(size_t i=0;i<source_frames*channels;++i)
   if(!std::isfinite(original[i])||!std::isfinite(retrieved[i]))return 0;
 for(size_t i=0;i<output_frames;++i)
   if(!std::isfinite(pitch_hz[i])||pitch_hz[i]<0)return 0;
 try {
   std::vector<float> prepared(n);
   std::vector<int64_t> bins(output_frames);
   const double low=1127*std::log1p(50./700),high=1127*std::log1p(1100./700);
   for(size_t i=0;i<output_frames;++i) {
     const double hz=pitch_hz[i];
     double quantized=hz>0 ? (1127*std::log1p(hz/700)-low)*254/(high-low)+1 : 1;
     quantized=std::clamp(quantized,1.,255.);
     // Explicit nearest-even rounding agrees with numpy.rint regardless of fenv.
     const double floorValue=std::floor(quantized),fraction=quantized-floorValue;
     int64_t bin=static_cast<int64_t>(floorValue);
     if(fraction>.5||(fraction==.5&&(bin&1)))++bin;
     bins[i]=bin;
     const double weight=protect<.5f&&hz<1 ? protect:1.;
     for(size_t j=0;j<channels;++j) {
       size_t src=(i/2)*channels+j;
       double value=double(retrieved[src])*weight+double(original[src])*(1-weight);
       float f=static_cast<float>(value);
       if(!std::isfinite(f))return 0;
       prepared[i*channels+j]=f;
     }
   }
   std::memcpy(output,prepared.data(),n*sizeof(float));
   std::memcpy(coarse,bins.data(),output_frames*sizeof(int64_t));
   return 1;
 } catch(...) {return 0;}
}
