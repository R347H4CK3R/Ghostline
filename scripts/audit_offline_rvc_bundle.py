#!/usr/bin/env python3
"""Audit bundled RVC WebAssembly assets, not offline audio generation.

Generate before IPA packaging:
  python3 scripts/audit_offline_rvc_bundle.py build/rvc-web-dist --write
Verify the exact copy in the IPA's .app directory:
  python3 scripts/audit_offline_rvc_bundle.py build/Build/Products/Release-iphoneos/GHOSTLINE.app/RVCWeb --verify

This script reads no private voices or model files and uses no network.
"""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
from urllib.parse import unquote, urlsplit

MANIFEST_NAME = "GHOSTLINE-RVC-ASSET-MANIFEST.json"
LICENSE_NAME = "THIRD_PARTY_RVC_WEB_RUNTIME_LICENSE.txt"


class LocalResources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        key = "src" if tag == "script" else "href" if tag == "link" else None
        if key and values.get(key):
            self.references.append(values[key])


def validated_reference(value, root):
    """Require HTML entrypoint scripts/styles to be bundled locally."""
    split = urlsplit(value)
    if split.scheme or split.netloc or value.startswith("//") or "\\" in value:
        raise ValueError(f"External or invalid asset URL: {value!r}")
    path = unquote(split.path)
    if not path or path.startswith("/") or "\0" in path:
        raise ValueError(f"Non-relative asset URL: {value!r}")
    normalized = posixpath.normpath(path)
    if normalized in ("", ".", "..") or normalized.startswith("../"):
        raise ValueError(f"Escaping asset URL: {value!r}")
    file = root / normalized
    if not file.is_file() or file.is_symlink():
        raise ValueError(f"Missing or unsafe bundled asset: {value!r}")
    return normalized


def create_manifest(directory):
    root = directory.resolve(strict=True)
    index = root / "index.html"
    worker = root / "inference.worker.js"
    license_file = root / LICENSE_NAME
    for path in (index, worker, license_file):
        if not path.is_file() or path.is_symlink() or path.stat().st_size < 20:
            raise ValueError(f"Missing or empty RVC asset: {path.name}")
    if "MIT License" not in license_file.read_text(encoding="utf-8"):
        raise ValueError("Bundled upstream license must contain MIT notice")
    parser = LocalResources()
    parser.feed(index.read_text(encoding="utf-8"))
    if not parser.references:
        raise ValueError("HTML entrypoint has no local resource references")
    linked = [validated_reference(value, root) for value in parser.references]
    if not any(value.endswith(".js") for value in linked):
        raise ValueError("HTML entrypoint has no local JS bundle")
    wasm_files = list((root / "onnx-wasm").rglob("*.wasm"))
    if not wasm_files:
        raise ValueError("ONNX WebAssembly backend absent")
    for file in wasm_files:
        if file.is_symlink() or not file.is_file() or file.stat().st_size < 16:
            raise ValueError(f"Invalid WebAssembly resource: {file}")
        with file.open("rb") as stream:
            if stream.read(4) != b"\x00asm":
                raise ValueError(f"Invalid WASM magic: {file}")
    files = []
    forbidden = {".pth", ".index", ".onnx", ".mp3", ".m4a", ".wav"}
    for file in sorted(root.rglob("*")):
        if file.is_symlink():
            raise ValueError(f"Symlink inside offline bundle: {file}")
        if not file.is_file() or file.name == MANIFEST_NAME:
            continue
        if file.suffix.lower() in forbidden:
            raise ValueError(f"Model or private voice input accidentally bundled: {file.name}")
        relative = file.relative_to(root).as_posix()
        size = file.stat().st_size
        if size == 0:
            raise ValueError(f"Empty bundled resource: {relative}")
        with file.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append({"path": relative, "bytes": size, "sha256": sha})
    return {
        "schema_version": 1,
        "kind": "asset_integrity_only_not_iPhone_inference_evidence",
        "upstream": "https://github.com/moyue23/rvc-web-runtime",
        "includes_private_voice_models": False,
        "target_device_audio_verified": False,
        "assets": files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    manifest = create_manifest(args.bundle)
    location = args.bundle / MANIFEST_NAME
    if args.write:
        location.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif not location.exists() or json.loads(location.read_text(encoding="utf-8")) != manifest:
        raise ValueError("RVC asset manifest missing or mismatched: reject unsigned IPA")
    total_bytes = sum(item["bytes"] for item in manifest["assets"])
    print(f"RVC asset audit passed: {len(manifest['assets'])} files, {total_bytes} bytes; "
          "no private model inputs included; iPhone generation remains unverified")


if __name__ == "__main__":
    main()
