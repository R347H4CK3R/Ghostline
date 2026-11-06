#!/usr/bin/env python3
"""Generate the approved purple Ghostline app icon from the checked-in art."""
import base64
import hashlib
import json
import subprocess
from pathlib import Path

root = Path("Ghostline/Assets.xcassets/AppIcon.appiconset")
root.mkdir(parents=True, exist_ok=True)
source = Path("Ghostline/Artwork/ghostline-approved-icon.jpg.base64")
jpg = root / "GhostlineSource.jpg"
jpg.write_bytes(base64.b64decode(source.read_text().strip(), validate=True))
if jpg.stat().st_size < 1000:
    raise RuntimeError("Approved icon source unexpectedly small")
output = root / "Icon1024.png"
subprocess.run(["sips", "-s", "format", "png", "-z", "1024", "1024",
                str(jpg), "--out", str(output)], check=True)
if output.stat().st_size < 10000:
    raise RuntimeError("Generated PNG icon unexpectedly small")
(root / "Contents.json").write_text(json.dumps({
    "images": [{"filename": "Icon1024.png", "idiom": "universal",
                "platform": "ios", "size": "1024x1024"}],
    "info": {"author": "xcode", "version": 1}
}, indent=2) + "\n")
jpg.unlink()
print("Approved Ghostline app icon generated:", output,
      output.stat().st_size, hashlib.sha256(output.read_bytes()).hexdigest())
