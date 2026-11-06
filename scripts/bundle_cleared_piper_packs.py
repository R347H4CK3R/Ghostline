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
    assert len(catalog["models"]) > 0  # initial four entries, no cap
    revision = catalog["source_revision"]
    assert re.fullmatch(r"[a-f0-9]{40}", revision)
    names = set()
    root.mkdir(parents=True, exist_ok=True)
    for pack in catalog["models"]:
        key = pack["id"]
        assert re.fullmatch(r"(?:en_(?:US|GB)-[a-z]+-medium|es_ES-carlfm-x_low)", key), key
        assert key not in names
        names.add(key)
        assert pack["device_status"] == "UNVERIFIED_CANDIDATE"
        assert pack["claimed_real_person_identity"] is None
        assert pack["dataset_license"] == "public domain"
        assert "Trained from scratch" in pack["training_lineage"]
        assert pack["speaker_ids"] == [0]
        folder = root / key
        folder.mkdir(exist_ok=True)
        assert {f["name"] for f in pack["files"]} == {
            "model.onnx", "model.onnx.json", "MODEL_CARD"}
        for item in pack["files"]:
            assert re.fullmatch(r"[a-f0-9]{64}", item["sha256"])
            assert item["size"] > 0
            assert item["upstream_path"].startswith(("en/", "es/"))
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
        config = json.loads((folder / "model.onnx.json").read_text())
        if config.get("num_speakers", 1) != 1:
            raise RuntimeError(f"Expected 1 speaker in {key}, got {config.get('num_speakers')}")
        card = (folder / "MODEL_CARD").read_text()
        if "public domain" not in card.lower() or "trained from scratch" not in card.lower():
            raise RuntimeError(f"License/lineage verification failed: {key}")
        print(f"{key}: model_sha256={pack['files'][0]['sha256']} speakerIDs=1 UNVERIFIED")
    all_models = ", ".join(pack["id"] for pack in catalog["models"])
    notice = (f"GHOSTLINE {len(catalog['models'])} OPEN-LICENSE PIPER TEST PACKS — UNVERIFIED\n"
              f"Models: {all_models}.\n"
              "Model repository: rhasspy/piper-voices (MIT), pinned revision "
              f"{revision}.\n"
              "Each bundled MODEL_CARD reports public-domain source recordings and"
              " from-scratch training. The Piper runtime has separate GPL obligations.\n"
              "These are synthetic voices, NOT authenticated movie, singer, actor,"
              " game, celebrity or character clones. Device offline audio and human"
              " listening have NOT been verified.\n"
              "Reference full per-file attribution, source and SHA-256 in manifest.json.\n")
    manifest_path = root / "manifest.json"
    notice_path = root / "ATTRIBUTION.txt"
    if args.verify:
        if json.loads(manifest_path.read_text()) != catalog or notice_path.read_text() != notice:
            raise RuntimeError("Bundled attribution or manifest mismatches pinned source")
    else:
        manifest_path.write_text(json.dumps(catalog, sort_keys=True, indent=2) + "\n")
        notice_path.write_text(notice)
    print(f"{len(catalog['models'])} open-license candidate packs; 0 device-verified voices.")


if __name__ == "__main__":
    main()
