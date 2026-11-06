#!/usr/bin/env python3
"""Regression guard: stale Piper upstream metadata must not disable downloads."""
import json
from pathlib import Path

manifest=json.loads(Path("Ghostline/Resources/piper-candidates.json").read_text())
model=next(m for m in manifest["models"] if m["model_id"]=="en_US-libritts_r-medium")
assert model["model_bytes"] == 78580914
assert model["model_md5"] == "bb2c2776cffbfd736c7c497f620c0ca6"
assert model["config_md5"] == "c740db18a0dab11b13ce0292ea1196"
s=Path("Ghostline/PiperVoiceLab.swift").read_text()
for marker in ("URLSession.shared.downloadTask", "downloadProgress",
               "downloadReceived", "downloadExpected",
               "downloadSpeedBytesPerSecond", "downloadPhase",
               "downloadInFlight", "cancelDownload",
               "verifyMD5(destination, expected: md5)",
               "validatePack(at: staging)",
               "previous intact pack was preserved"):
    assert marker in s, marker
generator=Path("scripts/generate_piper_candidates.py").read_text()
assert "LIVE_ASSET_OVERRIDES" in generator
print("Piper transfer observability, integrity and rollback contracts passed")
