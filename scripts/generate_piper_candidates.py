#!/usr/bin/env python3
"""Build an auditable Piper *candidate* catalog. Not a list of verified voices."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

SOURCE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
ASSETS = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
MAX_SPEAKERS_PER_MODEL = 32

# The upstream voices.json index is stale for this model (reports 2,306
# speakers and checksums that do not match its actual hosted assets).
# Verified against the immutable 2026-11-02 Hugging Face repository revision.
FEATURED_MODEL = "en_US-libritts_r-medium"
FEATURED_REVISION = "e7229f7d33a10e145e109b886d661984201ac3c4"
FEATURED_ASSETS = (
    f"https://huggingface.co/rhasspy/piper-voices/resolve/{FEATURED_REVISION}/"
)
FEATURED_MODEL_BYTES = 78580914
FEATURED_MODEL_MD5 = "bb2c2776cffbfd736c7c497f620c0ca6"
FEATURED_CONFIG_MD5 = "c740db18a0dab11b13ce0292ea1196c6"

def build():
    with urllib.request.urlopen(SOURCE, timeout=60) as response:
        raw = response.read()
    models = json.loads(raw)
    if not isinstance(models, dict) or len(models) < 150:
        raise ValueError("Piper model source incomplete")
    candidates = []
    model_inventory = []
    for key, info in sorted(models.items()):
        files = info.get("files", {})
        model_paths = [p for p in files if p.endswith(".onnx")]
        config_paths = [p for p in files if p.endswith(".onnx.json")]
        if len(model_paths) != 1 or len(config_paths) != 1:
            continue
        model_path = model_paths[0]
        config_path = config_paths[0]
        model_bytes = files[model_path].get("size_bytes")
        if not isinstance(model_bytes, int) or model_bytes <= 0:
            continue
        indexed_speakers = max(1, int(info.get("num_speakers", 1) or 1))
        featured = key == FEATURED_MODEL
        if featured:
            config_url = FEATURED_ASSETS + config_path
            with urllib.request.urlopen(config_url, timeout=60) as response:
                config_bytes = response.read()
            if hashlib.md5(config_bytes).hexdigest() != FEATURED_CONFIG_MD5:
                raise ValueError("Pinned LibriTTS-R config hash mismatch")
            num_speakers = int(json.loads(config_bytes)["num_speakers"])
            if num_speakers < 500:
                raise ValueError("Pinned LibriTTS-R has fewer than 500 speakers")
            model_bytes = FEATURED_MODEL_BYTES
        else:
            num_speakers = indexed_speakers
        selected = min(MAX_SPEAKERS_PER_MODEL, num_speakers)
        lang = info.get("language", {})
        speaker_map = info.get("speaker_id_map") or {}
        speaker_names = {int(v): k for k, v in speaker_map.items() if isinstance(v, int)}
        model_inventory.append({
            "model_id": key,
            "language": lang.get("code", ""),
            "quality": info.get("quality", ""),
            "declared_speakers": num_speakers,
            "speaker_count_source": "verified_config" if featured else "index_unverified",
            "index_declared_speakers": indexed_speakers,
            "candidate_speakers": selected,
            "model_bytes": model_bytes,
            "model_url": (FEATURED_ASSETS if featured else ASSETS) + model_path,
            "config_url": (FEATURED_ASSETS if featured else ASSETS) + config_path,
            "model_md5": FEATURED_MODEL_MD5 if featured else files[model_path].get("md5_digest"),
            "config_md5": FEATURED_CONFIG_MD5 if featured else files[config_path].get("md5_digest"),
            "license": "REVIEW_MODEL_CARD",
            "model_card_url": ASSETS + next((p for p in files if p.endswith("MODEL_CARD")), ""),
        })
        for speaker_id in range(selected):
            candidates.append({
                "id": f"piper/{key}/{speaker_id}",
                "engine": "piper",
                "model_id": key,
                "speaker_id": speaker_id,
                "speaker_label": speaker_names.get(speaker_id, f"Speaker {speaker_id + 1}"),
                "language": lang.get("code", ""),
                "quality": info.get("quality", ""),
                "availability": "candidate_unverified",
                "license": "review_required",
            })
    if len(candidates) < 500:
        raise ValueError("Candidate count has fallen below 500")
    return {
        "schema_version": 1,
        "source": SOURCE,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "description": "Candidate only. Counts do NOT prove distinctiveness, licensing or offline iPhone audio.",
        "model_count": len(model_inventory),
        "speaker_candidate_count": len(candidates),
        "max_speakers_per_model": MAX_SPEAKERS_PER_MODEL,
        "models": model_inventory,
        "candidates": candidates,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="Ghostline/Resources/piper-candidates.json")
    args = parser.parse_args()
    data = build()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Candidate catalog: {data['model_count']} Piper models, {data['speaker_candidate_count']} candidate speaker slots")
    print("Verified functional iPhone Piper voices: 0 (no target-device evidence received)")
    print(f"SHA256 source: {data['source_sha256']}")

if __name__ == "__main__":
    main()
