"""Publish only the 0.4.3 IPA whose native gates and playback source have passed."""
import base64, datetime, hashlib, json, os, pathlib, shutil, subprocess
from tools.verify_character_kit import verify
from tools.character_package import inspect_ipa
from tools.character_evidence import digest

REPO = "R347H4CK3R/Ghostline"
VERSION = "0.4.3"
TAG = "voicematrix-v0.4.3"
IPA = "VoiceMatrix-0.4.3.ipa"
TESTED = "07b9e7edb8f548c9d17318480080f30bd6f0de87"
ROOT = pathlib.Path("release-evidence")
NOTES = """VoiceMatrix 0.4.3

Playback: visible errors and Stop beside reference listening, selected-character guidance, output route/volume and elapsed-time diagnostics, and safer native player lifecycle.

Updates: Settings → Check for Updates can check this repository's published feed, download the IPA, or copy its link and switch to Strata. Strata finishes installation after VoiceMatrix exits. Replace the existing VoiceMatrix app and keep its existing data container; do not delete the app first.

Verification: ARM64 compilation; simulator imported-reference playback progress/replay, updater validation and UI checks; source/packaging regressions; hosted native F5 speech and simulator neural conversion with independent word/audio checks; exact-source package evidence and zero-stock/private-audio archive audit.

Physical iPhone/Strata audibility, update handoff, performance and individual character resemblance remain unverified. These hosted results do not establish that the reported iPhone silence is fixed. No character voices, private references or recordings are bundled. Existing imported data and pairing remain in the existing data container.
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
    for run_id in (42510504584, 42510504698):
        run = api(f"repos/{REPO}/actions/runs/{run_id}")
        assert run["head_sha"] == TESTED and run["conclusion"] == "success"
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
           "--repo", REPO, "--target", source, "--title", "VoiceMatrix 0.4.3 — playback controls and in-app updates",
           "--notes-file", str(notes))
    published = ROOT / "published"
    published.mkdir(exist_ok=True)
    gh("release", "download", TAG, "--repo", REPO, "-p", IPA, "-D", str(published), "--clobber")
    assert digest(published / IPA) == report["ipaSHA256"], "Published bytes differ from verified IPA"
    dependency = json.loads((ROOT / "ipa/dependency-notices.json").read_text())["proof"]
    inspect_ipa(published / IPA, dependency_proof=dependency, expected_version=VERSION)
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{IPA}"
    description = "Playback controls and diagnostics, character-selection guidance, and in-app update checks/downloads with Strata handoff. No stock voices or private character audio bundled. Native/simulator checks passed; physical iPhone sound and character likeness remain unverified."
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
        payload = dict(message="Publish verified VoiceMatrix 0.4.3 update feed", branch="main", sha=current["sha"],
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
