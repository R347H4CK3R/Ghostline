#!/usr/bin/env python3
"""Embed one rights-documented unverified Piper multispeaker pack for offline iPhone tests.

This script does not claim voice identity, listening quality, or iPhone verification.
Files are pinned to a single immutable upstream revision with byte length and MD5.
"""
import hashlib
import json
import urllib.request
from pathlib import Path

REV = "e7229f7d33a10e145e109b886d661984201ac3c4"
ROOT = f"https://huggingface.co/rhasspy/piper-voices/resolve/{REV}/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx"
OUT = Path("build/embedded-piper")
MODELS = [
    ("model.onnx", ROOT, 78580914, "bb2c2776cffbfd736c7c497f620c0ca6"),
    ("model.onnx.json", ROOT + ".json", 20123, "c740db18a0dab11b13ce0292ea1196c6"),
]
OUT.mkdir(parents=True, exist_ok=True)
for name, url, expected_size, expected_md5 in MODELS:
    target = OUT / name
    tmp = target.with_suffix(target.suffix + ".partial")
    md5 = hashlib.md5()
    size = 0
    with urllib.request.urlopen(url, timeout=180) as response, tmp.open("wb") as dst:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            md5.update(chunk)
            size += len(chunk)
    if size != expected_size or md5.hexdigest() != expected_md5:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Pinned voice model mismatch: {name}: bytes={size} md5={md5.hexdigest()}")
    tmp.replace(target)
    print(f"Verified included Piper file: {name}, {size} bytes, md5={md5.hexdigest()}")

config = json.loads((OUT / "model.onnx.json").read_text())
assert config["num_speakers"] == 904
assert len(config.get("speaker_id_map", {})) == 904
notice = (
    "GHOSTLINE OFFLINE TEST PACK — UNVERIFIED AUDIO\n"
    "Model: Piper en_US-libritts_r-medium, 904 speaker IDs; IDs are not authenticated voice identities.\n"
    f"Immutable source revision: https://huggingface.co/rhasspy/piper-voices/tree/{REV}\n"
    "Model card: https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/libritts_r/medium/MODEL_CARD\n"
    "Training dataset: LibriTTS-R, OpenSLR 141, CC BY 4.0, attribution required.\n"
    "Dataset URL: https://www.openslr.org/141/\n"
    "Model repository declares MIT; Piper inference software carries its own GPL licensing.\n"
    "No actual identity or offline audio has been device verified by inclusion.\n"
    "No unauthorized celebrity or character voice files are contained in this pack.\n"
)
(OUT / "ATTRIBUTION.txt").write_text(notice)
print("Embedded voice candidates in this model: 904 (all unverified)")
