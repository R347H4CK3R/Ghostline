#ifndef RVC_SYNTH_CORE_H
#define RVC_SYNTH_CORE_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Fixed-shape synthesizer boundary only; no speech-to-speech frontend. */
typedef struct RVCSynthSession RVCSynthSession;
typedef struct RVCCancel RVCCancel;
typedef enum {RVC_OK=0, RVC_INVALID_ARGUMENT, RVC_INVALID_MODEL, RVC_INVALID_TENSOR,
 RVC_INVALID_OUTPUT, RVC_CANCELLED, RVC_DEADLINE, RVC_BUSY, RVC_RUNTIME_ERROR} RVCStatus;
typedef enum {RVC_FLOAT32=1, RVC_INT64=2} RVCElementType;
typedef struct {
 const char* name;
 RVCElementType type;
 const int64_t* shape;
 size_t rank;
 const void* data;
 size_t bytes;
} RVCTensor;
/* Models must be trusted, hash-admitted and self-contained. No external assets.
 * Limits are I/O limits, NOT an allocator sandbox for hostile ONNX graphs.
 * No filesystem access is requested by this API. ORT may interpret graph content.
 * Session creation is synchronous and must not run on the main/UI thread.
 * Model buffer is borrowed for creation only; ORT owns its parsed session. */
RVCStatus rvc_synth_create(const void* model, size_t bytes, RVCSynthSession** result);
void rvc_synth_destroy(RVCSynthSession* session);
RVCCancel* rvc_cancel_create(void);
void rvc_cancel_request(RVCCancel* cancel);
void rvc_cancel_destroy(RVCCancel* cancel);
/* All pointers must reference their stated size, remain alive and immutable until
 * run returns. Destroy session/token only after all calls finish. A token is
 * one-shot. Cancellation/deadline use ORT cooperative termination, not hard RT.
 * One concurrent run per session; others return BUSY. timeout_ms:1..10000.
 * output_count must be40000. Failed runs do not modify the caller's output. */
RVCStatus rvc_synth_run(RVCSynthSession* session, const RVCTensor* tensors, size_t count,
 float* output, size_t output_count, RVCCancel* cancel, uint32_t timeout_ms);
const char* rvc_synth_runtime_version(void);
#ifdef __cplusplus
}
#endif
#endif
