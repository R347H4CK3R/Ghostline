#include "../Runner/pitch.h"
#include <array>
#include <cassert>
#include <limits>
int main(){
 std::array<float,48000> audio{};std::array<float,16384> out{};std::array<float,16> energy{},pitch{},confidence{};std::array<float,5760> salience{};
 assert(rvc_pitch_frames(audio.data(),48000,285,16,out.data(),energy.data()));
 assert(rvc_pitch_decode(salience.data(),16,energy.data(),50,1100,.1,.001,pitch.data(),confidence.data()));
 for(auto v:pitch)assert(v==0);
 out[0]=-99;audio.back()=std::numeric_limits<float>::quiet_NaN();assert(!rvc_pitch_frames(audio.data(),48000,0,16,out.data(),energy.data()));assert(out[0]==-99);
 assert(!rvc_pitch_frames(audio.data(),48001,0,1,out.data(),energy.data()));
 salience.back()=-1;pitch[0]=-99;assert(!rvc_pitch_decode(salience.data(),16,energy.data(),50,1100,.1,.001,pitch.data(),confidence.data()));assert(pitch[0]==-99);
}
