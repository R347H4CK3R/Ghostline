#!/usr/bin/env python3
"""Prepare or audit explicitly sourced public-domain-data Piper test packs.

No identity voice is attested; these files are bundled only into experimental
unsigned workflow artifacts. Never publish a release or substitute unknown files.
"""
import argparse
import hashlib
import json
import re
import shutil
import urllib.request
from pathlib import Path

SOURCE = Path("Ghostline/Resources/approved-piper-bundle.json")
DEFAULT_OUT = Path("build/embedded-piper")


def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def checked_file(path, item):
    return (path.is_file() and path.stat().st_size == item["size"]
            and digest_file(path) == item["sha256"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--directory", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    root = Path(args.directory)
    catalog = json.loads(SOURCE.read_text(encoding="utf-8"))
    assert catalog["schema_version"] == 1
    assert catalog["verified_identity_count"] == 0
    assert catalog["device_verified_audio_count"] == 0
    assert catalog["repo_license"] == "MIT"
    assert len(catalog["models"]) > 0  # variable inventory, no arbitrary cap
    revision = catalog["source_revision"]
    assert re.fullmatch(r"[a-f0-9]{40}", revision)
    quarantine = json.loads(Path("Ghostline/Resources/quarantined-piper-candidates.json").read_text(encoding="utf-8"))
    assert quarantine["schema_version"] == 1 and quarantine["source_revision"] == revision
    held_ids = {item["id"] for item in quarantine["models"]}
    assert len(held_ids) == len(quarantine["models"])
    assert all(item["rights_review"]["not_for_distribution"] is True for item in quarantine["models"])
    assert held_ids.isdisjoint({item["id"] for item in catalog["models"]}), "Provenance hold leaked into distribution manifest"
    names = set()
    root.mkdir(parents=True, exist_ok=True)
    for pack in catalog["models"]:
        key = pack["id"]
        match = re.fullmatch(r"([a-z]{2})_([A-Z]{2})-([a-z0-9_]+)-(x_low|low|medium|high)", key)
        assert match, key
        family, region, voice, quality = match.groups()
        prefix = f"{family}/{family}_{region}/{voice}/{quality}/"
        assert pack["engine"] == "piper" and pack["language"] == f"{family}_{region}"
        assert pack["category"] == "open_licensed_synthetic"
        assert pack["model_card_url"] == (
            f"https://huggingface.co/rhasspy/piper-voices/blob/{revision}/{prefix}MODEL_CARD")
        assert key not in names
        names.add(key)
        assert pack["device_status"] == "UNVERIFIED_CANDIDATE"
        assert pack["claimed_real_person_identity"] is None
        review = pack["rights_review"]
        assert review["decision"] == "SOURCE_DOCUMENTED_EXPERIMENTAL_ONLY", key
        assert review["model_card_url"] == pack["model_card_url"], key
        assert review["dataset_evidence_url"].startswith("https://"), key
        assert review["identity_permissions_independently_verified"] is False, key
        assert review["device_generation_verified"] is False, key
        assert pack["dataset_license"] in ("public domain", "CC0", "CC0 1.0 Universal")
        assert "MIT" in pack["license"]
        assert "Trained from scratch" in pack["training_lineage"]
        assert pack["speaker_ids"] and pack["speaker_ids"] == list(range(len(pack["speaker_ids"])))
        folder = root / key
        folder.mkdir(exist_ok=True)
        assert {f["name"] for f in pack["files"]} == {
            "model.onnx", "model.onnx.json", "MODEL_CARD"}
        for item in pack["files"]:
            assert re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
            assert item["size"] > 0
            expected_upstream = {
                "model.onnx": prefix + key + ".onnx",
                "model.onnx.json": prefix + key + ".onnx.json",
                "MODEL_CARD": prefix + "MODEL_CARD",
            }[item["name"]]
            assert item["upstream_path"] == expected_upstream, key
            dst = folder / item["name"]
            if checked_file(dst, item):
                continue
            if args.verify:
                raise RuntimeError(f"Missing/corrupt package asset: {dst}")
            url = ("https://huggingface.co/rhasspy/piper-voices/resolve/"
                   f"{revision}/{item['upstream_path']}")
            tmp = dst.with_name(dst.name + ".partial")
            h = hashlib.sha256()
            size = 0
            try:
                with urllib.request.urlopen(url, timeout=180) as response, tmp.open("wb") as out:
                    for chunk in iter(lambda: response.read(1024 * 1024), b""):
                        size += len(chunk)
                        h.update(chunk)
                        out.write(chunk)
                if size != item["size"] or h.hexdigest() != item["sha256"]:
                    raise ValueError(f"Upstream bytes do not match pin: {key}/{item['name']}")
                tmp.replace(dst)
            finally:
                tmp.unlink(missing_ok=True)
            if not checked_file(dst, item):
                raise RuntimeError(f"Post-copy verification failed: {dst}")
        config = json.loads((folder / "model.onnx.json").read_text(encoding="utf-8"))
        if config.get("num_speakers", 1) != len(pack["speaker_ids"]):
            raise RuntimeError(f"Speaker count mismatch for {key}: expected {pack['speaker_ids']}, got {config.get('num_speakers')}")
        if config.get("speaker_id_map"):
            assert sorted(config["speaker_id_map"].values()) == pack["speaker_ids"]
        card = (folder / "MODEL_CARD").read_text(encoding="utf-8")
        if (pack["dataset_license"].lower() not in card.lower()
                or "trained from scratch" not in card.lower()):
            raise RuntimeError(f"License/lineage verification failed: {key}")
        print(f"{key}: model_sha256={pack['files'][0]['sha256']} speakerIDs={len(pack['speaker_ids'])} UNVERIFIED")
    all_models = ", ".join(pack["id"] for pack in catalog["models"])
    notice = (f"GHOSTLINE {len(catalog['models'])} OPEN-LICENSE PIPER TEST PACKS — UNVERIFIED\n"
              f"Models: {all_models}.\n"
              "Model repository: rhasspy/piper-voices (MIT), pinned revision "
              f"{revision}.\n"
              "Each bundled MODEL_CARD reports public-domain/CC0 recordings and"
              " from-scratch training. The Piper runtime has separate GPL obligations.\n"
              "These are synthetic voices, NOT authenticated movie, singer, actor,"
              " game, celebrity or character clones. Device offline audio and human"
              " listening have NOT been verified.\n"
              "Reference full per-file attribution, source and SHA-256 in manifest.json.\n")
    manifest_path = root / "manifest.json"
    notice_path = root / "ATTRIBUTION.txt"
    if args.verify:
        if json.loads(manifest_path.read_text(encoding="utf-8")) != catalog or notice_path.read_text(encoding="utf-8") != notice:
            raise RuntimeError("Bundled attribution or manifest mismatches pinned source")
    else:
        manifest_path.write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        notice_path.write_text(notice, encoding="utf-8")
    print(f"{len(catalog['models'])} open-license candidate packs, "
          f"{sum(len(p['speaker_ids']) for p in catalog['models'])} unverified speaker slots; "
          "0 device-verified voices.")


if __name__ == "__main__":
    main()
