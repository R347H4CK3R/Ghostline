#ifndef RVC_FEATURES_H
#define RVC_FEATURES_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Explicit contiguous arrays: original/retrieved [source_frames, channels],
 pitch_hz [output_frames], output [output_frames,channels], coarse [output_frames].
 output_frames must equal 2*source_frames; frames <=1000, channels <=768.
 Returns 1 only after committing both outputs, 0 preserves both on rejection.
 Caller owns valid-sized buffers. Outputs must not overlap each other.
 No pitch estimation, model admission, embedding, or retrieval search is performed. */
int rvc_prepare_features(const float *original,const float *retrieved,size_t source_frames,
 size_t channels,const float *pitch_hz,size_t output_frames,float protect,
 float *output,int64_t *coarse);
#ifdef __cplusplus
}
#endif
#endif
