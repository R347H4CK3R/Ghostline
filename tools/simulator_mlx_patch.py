"""CI-only experiment: retain MLX shared buffers, skip unsupported simulator heap.

Never invoked by IPA packaging. Device compilation remains unchanged. This uses
the allocator's existing no-heap fallback, also used for Apple virtual devices.
It does not replace audio, disable Metal validation, or claim device equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_SHA256 = '2e7ea0bccec1c2e2b962b579f838b8d088b7197f1c7c2cda98535c9b53070dd0'

def patch_source(source):
    if hashlib.sha256(source.encode()).hexdigest() != EXPECTED_SHA256:
        raise ValueError('Unrecognized MLX allocator source; refusing diagnostic patch')
    marker = '  if (is_vm) {\n    return;\n  }'
    if source.count(marker) != 1:
        raise ValueError('Expected one virtual-device heap guard')
    return source.replace('#include "mlx/backend/metal/allocator.h"', '#include "mlx/backend/metal/allocator.h"\n#include <TargetConditionals.h>', 1).replace(marker, marker + '\n#if TARGET_OS_SIMULATOR\n  return; // Simulator Metal supports shared buffers, not shared heaps.\n#endif', 1)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkouts', type=Path)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    candidates = list(args.checkouts.glob('mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/allocator.cpp'))
    if len(candidates) != 1:
        raise SystemExit('Expected one resolved mlx-swift allocator')
    target = candidates[0]
    original = target.read_text()
    modified = patch_source(original)
    target.write_text(modified)
    args.evidence.write_text(json.dumps({'scope':'simulator-only diagnostic; never release packaging', 'upstreamMLXRevision':'ce45c52505c8158ea48d2a54e8caae05efd86bfe', 'originalSHA256':hashlib.sha256(original.encode()).hexdigest(), 'modifiedSHA256':hashlib.sha256(modified.encode()).hexdigest(), 'sharedBufferAllocationPreserved':True, 'physicalDeviceValidated':False}, indent=2) + '\n')

if __name__ == '__main__':
    main()
