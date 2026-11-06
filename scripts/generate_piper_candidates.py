#!/usr/bin/env python3
"""Build an auditable Piper *candidate* catalog. Not a list of verified voices."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

SOURCE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/voices.json"
ASSETS = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"

# The upstream voices.json inventory can lag the actual downloadable ONNX
# objects. These values were independently downloaded and hashed on 2026-11-06.
# Do not silently revert a corrected checksum when regenerating the catalog.
LIVE_ASSET_OVERRIDES = {
    "en_US-libritts_r-medium": {
        "model_bytes": 78580914,
        "model_md5": "bb2c2776cffbfd736c7c497f620c0ca6",
        "config_md5": "c740db18a0dab11b13ce0292ea1196",
    }
}

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
        num_speakers = max(1, int(info.get("num_speakers", 1) or 1))
        # Index all declared slots. The installed model config determines which
        # speaker IDs are actually executable; this source registry can differ.
        selected = num_speakers
        lang = info.get("language", {})
        speaker_map = info.get("speaker_id_map") or {}
        speaker_names = {int(v): k for k, v in speaker_map.items() if isinstance(v, int)}
        model_inventory.append({
            "model_id": key,
            "language": lang.get("code", ""),
            "quality": info.get("quality", ""),
            "declared_speakers": num_speakers,
            "candidate_speakers": selected,
            "model_bytes": model_bytes,
            "model_url": ASSETS + model_path,
            "config_url": ASSETS + config_path,
            "model_md5": files[model_path].get("md5_digest"),
            "config_md5": files[config_path].get("md5_digest"),
            "license": "REVIEW_MODEL_CARD",
            "model_card_url": ASSETS + next((p for p in files if p.endswith("MODEL_CARD")), ""),
        })
        model_inventory[-1].update(LIVE_ASSET_OVERRIDES.get(key, {}))
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
        "speaker_ids_truncated": False,
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
    print("Verified offline iPhone identities: 0 (metadata regeneration is not device audio testing)")
    print(f"SHA256 source: {data['source_sha256']}")

if __name__ == "__main__":
    main()
