#!/usr/bin/env python3
"""Package a pinned MIT-licensed browser RVC engine for fully local WKWebView use.

This pulls source only in CI, bundles JS and WASM in the IPA, and disables
remote model discovery. Users import their own licensed models at runtime.
"""
from pathlib import Path
import subprocess
import shutil
import textwrap

UPSTREAM = "https://github.com/moyue23/rvc-web-runtime.git"
COMMIT = "bed1e46d1a4e0ba8a47dd13975a467e5e8c88d62"
root = Path("build/rvc-web-src").resolve()
root.parent.mkdir(parents=True, exist_ok=True)
if root.exists():
    shutil.rmtree(root)
root.mkdir(parents=True)
subprocess.run(["git", "init", "-q"], cwd=root, check=True)
subprocess.run(["git", "remote", "add", "origin", UPSTREAM], cwd=root, check=True)
subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", COMMIT], cwd=root, check=True)
subprocess.run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=root, check=True)
actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
assert actual == COMMIT, "RVC upstream commit mismatch"

app = root / "packages/app"
(app / "src/main.ts").write_text(textwrap.dedent(r'''
import { prepareInputAudio } from "../../engine/src/audio";
import { runPipelineInWorker } from "../../engine/src/worker/client";
import { createRVC } from "../../engine/src/rvc";

const $ = <T extends HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) throw new Error("Missing control " + id);
  return element as T;
};

const status = (message: string): void => {
  $<HTMLElement>("status").textContent = message;
  const label = message.length > 200 ? message.slice(0, 200) : message;
  window.webkit?.messageHandlers?.ghostline?.postMessage({ kind: "status", message: label });
};
declare global {
  interface Window {
    webkit?: { messageHandlers?: { ghostline?: { postMessage: (x: unknown) => void } } };
    __ghostlineImportedModelPath?: string;
  }
}

let outputURL: string | null = null;
const button = $<HTMLButtonElement>("convert");
button.addEventListener("click", async () => {
  if (button.disabled) return;
  let model = $<HTMLInputElement>("model").files?.[0];
  const contentVec = $<HTMLInputElement>("contentvec").files?.[0];
  const rmvpe = $<HTMLInputElement>("rmvpe").files?.[0];
  const audio = $<HTMLInputElement>("audio").files?.[0];
  if ((!model && !window.__ghostlineImportedModelPath) || !contentVec || !rmvpe || !audio) {
    status("Select an RVC v2 .pth/.onnx voice or an imported pack, ContentVec, RMVPE and source audio.");
    return;
  }
  button.disabled = true;
  const conversionID = crypto.randomUUID();
  // Clear stale browser playback and notify native code BEFORE asynchronous
  // inference; a failed new attempt must not inherit an old WAV attestation.
  window.webkit?.messageHandlers?.ghostline?.postMessage({
    kind: "conversion_started", conversionId: conversionID
  });
  if (outputURL) URL.revokeObjectURL(outputURL);
  outputURL = null;
  const previousPreview = $<HTMLAudioElement>("preview");
  previousPreview.pause();
  previousPreview.removeAttribute("src");
  previousPreview.load();
  const previousSave = $<HTMLAnchorElement>("save");
  previousSave.hidden = true;
  previousSave.removeAttribute("href");
  const time = performance.now();
  try {
    if (!model) {
      // Same-origin local URL supplied by the native RVC Pack Library. The
      // native server checks the stored SHA-256 before releasing any bytes.
      status("Loading imported private .pth candidate after integrity check...");
      const response = await fetch(window.__ghostlineImportedModelPath!, {
        cache: "no-store", credentials: "omit",
      });
      if (!response.ok) throw new Error("Private imported model integrity or access failed (" + response.status + ")");
      const data = await response.blob();
      model = new File([data], "private-imported-candidate.pth", { type: "application/octet-stream" });
    }
    if (!/\.(pth|onnx)$/i.test(model.name) || [contentVec, rmvpe].some(x => !x.name.toLowerCase().endsWith(".onnx"))) {
      throw new Error("RVC voice must be .pth or .onnx; ContentVec and RMVPE must be .onnx.");
    }
    status("Decoding source audio on your iPhone...");
    const decoded = await prepareInputAudio(audio);
    const origin = new URL("./", location.href).href;
    const engine = createRVC({
      assetBaseUrl: origin,
      wasmBaseUrl: new URL("onnx-wasm/", origin).href,
    });
    status("Running offline ContentVec → RMVPE → RVC synthesis...");
    const result = await runPipelineInWorker(
      engine,
      { model, contentVec, rmvpe },
      decoded.audio,
      decoded.sampleRate,
      { onEvent(event) {
        if (event.type === "stage") status("Offline stage: " + event.stage);
        else if (event.type === "chunk") status("Converting chunk " + event.current + " / " + event.total);
      }},
      {
        rvcBackend: "wasm",
        contentVecBackend: "wasm",
        rmvpeBackend: "wasm",
        speakerId: Number($<HTMLInputElement>("speaker").value) || 0,
        pitchShift: Number($<HTMLInputElement>("pitch").value) || 0,
        timeout: 600000,
        chunkDuration: 12,
      },
    );
    if (result.state !== "success" || !result.outputWav) {
      throw new Error(result.errorMessage ?? "No converted WAV was returned.");
    }
    if (outputURL) URL.revokeObjectURL(outputURL);
    outputURL = URL.createObjectURL(result.outputWav);
    const player = $<HTMLAudioElement>("preview");
    player.src = outputURL;
    $<HTMLAnchorElement>("save").href = outputURL;
    $<HTMLAnchorElement>("save").hidden = false;
    const seconds = ((performance.now() - time) / 1000).toFixed(1);
    status("Converted locally in " + seconds + "s. Listen to verify voice quality.");
    if (window.webkit?.messageHandlers?.ghostline) {
      const reader = new FileReader();
      reader.onload = () => {
        window.webkit?.messageHandlers?.ghostline?.postMessage({
          kind: "wav", conversionId: conversionID, dataURL: reader.result,
          name: "GHOSTLINE-RVC-Converted.wav"
        });
      };
      reader.readAsDataURL(result.outputWav);
    }
  } catch (e) {
    status("Conversion failed: " + (e instanceof Error ? e.message : String(e)));
  } finally {
    button.disabled = false;
  }
});
''').strip() + "\n", encoding="utf-8")

(app / "index.html").write_text(textwrap.dedent('''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>GHOSTLINE Offline RVC</title>
<style>
:root{color-scheme:dark;font-family:-apple-system,BlinkMacSystemFont,system-ui;background:#110c1d;color:#f5f0ff}
body{margin:0;padding:16px 18px 40px}h1{font-size:24px;margin:0 0 8px}h2{font-size:14px;margin:0 0 12px}
p{color:#c6bcd8;font-size:13px;line-height:1.5}
.card{background:#20172f;border:1px solid #503761;border-radius:18px;padding:17px;margin:13px 0}
label{display:block;font-size:14px;font-weight:600;margin:14px 0 8px}
input[type=file],input[type=number]{box-sizing:border-box;width:100%;padding:12px;color:#fff;background:#140f22;border:1px solid #59436d;border-radius:11px}
input[type=range]{width:100%;accent-color:#ae71ff}button{border:0;background:#9a5af2;color:white;font-weight:800;padding:15px;border-radius:14px;width:100%}
button:disabled{opacity:.5}audio{width:100%;margin-top:12px}a{color:#d2acff}
.note{background:#171021;border-left:3px solid #9a5af2;padding:10px 13px;border-radius:8px}
</style>
</head>
<body>
<h1>GHOSTLINE • RVC</h1>
<p>Private, fully local RVC v2 audio conversion using a bundled WebAssembly inference engine. Internet is not needed once you supply compatible local models.</p>
<div class="card">
<h2>INPUT MODELS</h2>
<label for="model">RVC v2 voice (.pth or .onnx)</label><input id="model" type="file" accept=".pth,.onnx">
<p id="selected-pack">If opened from your RVC Pack Library, the selected private .pth is loaded after its import checksum is revalidated. Choosing a file here overrides it.</p>
<label for="contentvec">ContentVec 768-dimension encoder (.onnx)</label><input id="contentvec" type="file" accept=".onnx">
<label for="rmvpe">RMVPE pitch estimator (.onnx)</label><input id="rmvpe" type="file" accept=".onnx">
<label for="audio">Source vocal WAV / MP3</label><input id="audio" type="file" accept="audio/*,.wav,.mp3">
<label for="speaker">Speaker ID (model-specific)</label><input id="speaker" type="number" value="0" min="0">
<label for="pitch">Pitch shift in semitones</label><input id="pitch" type="number" value="0" min="-24" max="24">
</div>
<div class="card">
<button id="convert">Convert voice offline</button>
<p id="status">Choose models and audio. Nothing is uploaded.</p>
<audio id="preview" controls></audio>
<p><a id="save" href="#" download="GHOSTLINE-RVC-Converted.wav" hidden>Save converted WAV</a></p>
</div>
<p class="note">Only load voices and audio you are permitted to use. Imported files are candidate inputs, not verified voice identities. This engine supports RVC v2 .onnx or browser-convertible .pth models. The .pth conversion happens locally but may require substantial memory. iPhone WebAssembly performance and Strata support require device testing.</p>
<script type="module" src="/src/main.ts"></script>
</body>
</html>
''').strip() + "\n", encoding="utf-8")

vite = app / "vite.config.ts"
source = vite.read_text()
source = source.replace("export default defineConfig({", 'export default defineConfig({\n  base: "./",', 1)
vite.write_text(source)

subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=root, check=True)
subprocess.run(["npm", "run", "build:engine"], cwd=root, check=True)
subprocess.run(["npm", "run", "build:app"], cwd=root, check=True)

dist = app / "dist"
for relative in ["index.html", "inference.worker.js"]:
    assert (dist / relative).exists(), "Missing web runtime file " + relative
assert list((dist / "onnx-wasm").glob("*.wasm")), "No ONNX WASM backend bundled"
output = Path("build/rvc-web-dist").resolve()
if output.exists():
    shutil.rmtree(output)
shutil.copytree(dist, output)
shutil.copy2(root / "LICENSE", output / "THIRD_PARTY_RVC_WEB_RUNTIME_LICENSE.txt")
print("Bundled offline RVC web distribution:", output)
for p in sorted(output.rglob("*")):
    if p.is_file():
        print("  ", p.relative_to(output), p.stat().st_size)
