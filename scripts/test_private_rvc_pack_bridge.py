#!/usr/bin/env python3
"""Check private pack-to-converter plumbing; not an on-device inference test."""
from pathlib import Path
s = Path("Ghostline/OfflineRVCWeb.swift").read_text()
p = Path("Ghostline/RVCPackLibrary.swift").read_text()
b = Path("scripts/build_offline_rvc_web.py").read_text()
assert 'pack.weightFile == pack.id.uuidString + ".pth"' in s
assert 'privateModel = PrivateModel(' in s
assert 'size > 1024, size <= 1_000_000_000' in s
assert '(try? self.fileSHA256(candidate.file)) == candidate.sha256' in s
assert 'Cross-Origin-Resource-Policy: same-origin' in s
assert 'Cache-Control: no-store' in s
assert 'let route = "/private-candidate-" + UUID().uuidString + ".pth"' in s
assert 'GhostlineRVCWebScreen(importedPack: pack)' in p
assert 'window.__ghostlineImportedModelPath' in s
assert 'response = await fetch(window.__ghostlineImportedModelPath!' in b
assert 'new File([data], "private-imported-candidate.pth"' in b
assert 'if (!model)' in b
assert 'rvc_index_retrieval_integrated": false' in s
print("Private RVC candidate wiring, checksum, ephemeral route and no-index guards: PASS")
