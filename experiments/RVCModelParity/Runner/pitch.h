#ifndef RVC_PITCH_H
#define RVC_PITCH_H
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
// Mono16k PCM[-1,1], 1..48000samples, 1..16frames. Frames have1024samples,
// hop160, zero-pad512 each end. Output sizes: frames*1024 and frames AC RMS (mean removed).
// Inputs consumed before commit. Output buffers must not overlap. Invalid returns0.
int rvc_pitch_frames(const float*,size_t,size_t,size_t,float*,float*);
// Salience[frames,360] in[0,1]; bounded weighted9-bin decoder, no stochastic
// dither or Viterbi. Frequency range, confidence/RMS thresholds are explicit.
// Outputs pitchHz[frames] (0=unvoiced), confidence[frames]. Not identity evidence.
int rvc_pitch_decode(const float*,size_t,const float*,float,float,float,float,float*,float*);
#ifdef __cplusplus
}
#endif
#endif
