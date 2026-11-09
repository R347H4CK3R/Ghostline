"""Publish only the 0.4.5 IPA whose native gates and playback source have passed."""
import base64, datetime, hashlib, json, os, pathlib, shutil, subprocess, time
from tools.verify_character_kit import verify
from tools.character_package import inspect_ipa
from tools.character_evidence import digest

REPO = "R347H4CK3R/Ghostline"
VERSION = "0.4.5"
TAG = "voicematrix-v0.4.5"
IPA = "VoiceMatrix-0.4.5.ipa"
TESTED = "2c162e43caa157f18d78f6b5cd208af2bb48c2ce"
ROOT = pathlib.Path("release-evidence")
NOTES = """VoiceMatrix 0.4.5

Long speech now uses complete-word chunks with streamed output instead of a fixed character cap. A clear 30-minute raw-audio job budget protects memory and storage. Speed, pitch, volume and pause controls apply to saved and shared speech.

Suggestions open a GitHub draft with an explicit public-content acknowledgement. Only the text you enter is included; recordings, voices, speech text, logs and device identifiers are not automatically attached. You review and submit on GitHub.

Imported references, saved recordings and pairing remain in the existing data container. Replace the existing VoiceMatrix app in Strata and keep its data container; do not delete it first.

Verification includes native ARM64 compilation, actual offline audio effects, long-text chunking, cancellation cleanup, and 16 simulator checks covering playback, updates, import and relaunch preservation, controls and suggestion drafts. Native speech, conversion and package gates bind this IPA to the tested app source. No private character audio or stock profiles are bundled.

Physical iPhone playback, update handoff and individual character likeness still require device evaluation. Daily owner-suggestion review is configured; its first scheduled execution has not been verified.
"""

def gh(*args, check=True):
    return subprocess.run(["gh", *args], check=check, capture_output=True, text=True).stdout

def api(path):
    return json.loads(gh("api", path))

def version_key(entry):
    version = tuple(int(x) for x in entry["version"].split("."))
    return (version + (0,) * (4 - len(version)), int(entry.get("buildVersion", "0")))

def main():
    source = os.environ["GITHUB_SHA"]
    assert os.environ["GITHUB_REPOSITORY"] == REPO
    # The publication job depends on actual speech/conversion/package jobs.
    # Also bind the already-passed playback/updater tests to every shipped app source.
    for run_id, tested_sha in (
        (42555788134, "1996e7c58b1cb96971dc6e01c6e66a74f17903a9"),
        (42559606073, TESTED),
    ):
        deadline = time.monotonic() + 1200
        while True:
            run = api(f"repos/{REPO}/actions/runs/{run_id}")
            assert run["head_sha"] == tested_sha
            if run["status"] == "completed":
                assert run["conclusion"] == "success", f"Required check failed: {run_id}"
                break
            assert time.monotonic() < deadline, f"Required check still pending: {run_id}"
            time.sleep(20)
    subprocess.run(["git", "fetch", "--depth=1", "origin", TESTED], check=True)
    report = verify(ROOT / "ipa", ROOT / "speech", ROOT / "conversion", source, VERSION)
    proof = json.loads((ROOT / "ipa/source-proof.json").read_text())
    for path, expected in proof["files"].items():
        content = subprocess.check_output(["git", "show", f"{TESTED}:{path}"])
        assert hashlib.sha256(content).hexdigest() == expected, f"Shipped app differs from tested source: {path}"
    report.update(workflowRun=int(os.environ["GITHUB_RUN_ID"]), playbackTestSource=TESTED,
                  playbackAndUpdaterSimulatorTestsPassed=True)
    verification = ROOT / "character-release-verification.json"
    verification.write_text(json.dumps(report, indent=2) + "\n")
    public_ipa = ROOT / IPA
    shutil.copyfile(ROOT / f"ipa/VoiceMatrix-{VERSION}-character-test.ipa", public_ipa)
    notes = ROOT / "release-notes.txt"
    notes.write_text(NOTES)
    checksum = ROOT / (IPA + ".sha256")
    checksum.write_text(report["ipaSHA256"] + "  " + IPA + "\n")
    existing = gh("release", "view", TAG, "--repo", REPO, "--json", "tagName", check=False)
    if not existing:
        gh("release", "create", TAG, str(public_ipa), str(checksum), str(verification),
           str(ROOT / "ipa/dependency-notices.json"),
           str(ROOT / "speech/speech-evidence.json"),
           str(ROOT / "conversion/conversion-evidence/conversion-result.json"),
           "--repo", REPO, "--target", source, "--title", "VoiceMatrix 0.4.5 — long speech and audio controls",
           "--notes-file", str(notes))
    published = ROOT / "published"
    published.mkdir(exist_ok=True)
    gh("release", "download", TAG, "--repo", REPO, "-p", IPA, "-D", str(published), "--clobber")
    assert digest(published / IPA) == report["ipaSHA256"], "Published bytes differ from verified IPA"
    dependency = json.loads((ROOT / "ipa/dependency-notices.json").read_text())["proof"]
    inspect_ipa(published / IPA, dependency_proof=dependency, expected_version=VERSION)
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{IPA}"
    description = "Long speech with a practical 30-minute raw-audio budget; saved/shared speed, pitch, volume and pause controls; explicitly public suggestion drafts. Imported data preserved, no bundled stock voices. Native and simulator checks passed; physical iPhone evaluation remains pending."
    entry = dict(version=VERSION, buildVersion="1", date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                 downloadURL=url, localizedDescription=description, minOSVersion="26.0",
                 size=report["ipaBytes"], sha256=report["ipaSHA256"])
    feeds = {}
    for name in ("livecontainer-test.json", "source.json", "strata-source.json"):
        current = api(f"repos/{REPO}/contents/{name}?ref=main")
        feed = json.loads(base64.b64decode(current["content"]))
        matches = [x for x in feed["apps"] if x["bundleIdentifier"] == "com.voicematrix.app"]
        assert len(matches) == 1
        app = matches[0]
        assert not any(x.get("version") == VERSION and x.get("downloadURL") != url for x in app["versions"]), "Conflicting release; feed preserved"
        if any(version_key(x) > version_key(entry) for x in app["versions"]):
            feeds[name] = "newer release preserved"
            continue
        if app["versions"][0] == entry:
            feeds[name] = "already current"
            continue
        previous = [x for x in app["versions"] if x.get("downloadURL") != url]
        app["versions"] = [entry] + previous
        app["name"] = "VoiceMatrix"
        app["localizedDescription"] = description
        payload = dict(message="Publish verified VoiceMatrix 0.4.5 update feed", branch="main", sha=current["sha"],
                       content=base64.b64encode((json.dumps(feed, indent=2) + "\n").encode()).decode())
        request = ROOT / ("feed-" + name)
        request.write_text(json.dumps(payload))
        gh("api", "--method", "PUT", f"repos/{REPO}/contents/{name}", "--input", str(request))
        fresh = api(f"repos/{REPO}/contents/{name}?ref=main")
        actual = next(x for x in json.loads(base64.b64decode(fresh["content"]))["apps"] if x["bundleIdentifier"] == "com.voicematrix.app")
        assert actual["versions"][0] == entry and actual["versions"][1:] == previous
        feeds[name] = "published and read back"
    report.update(status="published-and-redownload-verified", url=url, tag=TAG, feeds=feeds)
    (ROOT / "publication-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
