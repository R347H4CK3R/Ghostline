#include "features.h"
#include <cassert>
#include <cmath>
#include <limits>
int main() {
 float a[4]={1,2,3,4},b[4]={11,12,13,14},p[4]={0,100,0,1100},out[8]={};int64_t bins[4]={};
 assert(rvc_prepare_features(a,b,2,2,p,4,.33f,out,bins)==1);
 assert(std::fabs(out[0]-4.3f)<1e-6&&out[2]==11&&bins[0]==1&&bins[3]==255);
 p[3]=std::numeric_limits<float>::quiet_NaN();out[0]=-999;bins[0]=-999;
 assert(rvc_prepare_features(a,b,2,2,p,4,.33f,out,bins)==0);
 assert(out[0]==-999&&bins[0]==-999);
 assert(rvc_prepare_features(a,b,501,2,p,1002,.33f,out,bins)==0);
 p[3]=1100;
 // Valid in-place input/output is staged until all source values are consumed.
 float aliased[8]={1,2,3,4,0,0,0,0};
 assert(rvc_prepare_features(aliased,b,2,2,p,4,.33f,aliased,bins)==1);
 assert(std::fabs(aliased[4]-6.3f)<1e-6&&aliased[6]==13);
 alignas(int64_t) unsigned char storage[64]={};
 assert(rvc_prepare_features(a,b,2,2,p,4,.33f,reinterpret_cast<float*>(storage),reinterpret_cast<int64_t*>(storage))==0);
 return 0;
}
