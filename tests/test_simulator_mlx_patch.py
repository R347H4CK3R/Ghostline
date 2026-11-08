import importlib.util
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('simulator_mlx_patch', Path(__file__).parents[1] / 'tools/simulator_mlx_patch.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class SimulatorMLXPatchTests(unittest.TestCase):
    def test_unknown_source_refused(self):
        with self.assertRaises(ValueError):
            m.patch_source('different upstream source')

    def test_only_simulator_skips_heap_and_shared_buffers_unchanged(self):
        source = '#include "mlx/backend/metal/allocator.h"\n  if (is_vm) {\n    return;\n  }\n  heap_ = device_->newHeap(heap_desc);\n  buf = device_->newBuffer(size, resource_options);\n'
        with patch.object(m, 'EXPECTED_SHA256', hashlib.sha256(source.encode()).hexdigest()):
            result = m.patch_source(source)
        self.assertIn('#include <TargetConditionals.h>', result)
        self.assertIn('#if TARGET_OS_SIMULATOR\n  return;', result)
        self.assertIn('  heap_ = device_->newHeap(heap_desc);', result)
        self.assertIn('  buf = device_->newBuffer(size, resource_options);', result)
        self.assertNotIn('StorageModePrivate', result)
