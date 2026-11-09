"""Publish only the 0.4.6 IPA whose native gates and playback source have passed."""
import base64, datetime, hashlib, json, os, pathlib, shutil, subprocess, time
from tools.verify_character_kit import verify
from tools.character_package import inspect_ipa
from tools.character_evidence import digest

REPO = "R347H4CK3R/Ghostline"
VERSION = "0.4.6"
TAG = "voicematrix-v0.4.6"
IPA = "VoiceMatrix-0.4.6.ipa"
TESTED = "5380abe47ea1bdee332128aa76ea53666b05f076"
CANDIDATE = "787737897ee3ddb419291caff32d8aec157a9931"
ROOT = pathlib.Path("release-evidence")
NOTES = """VoiceMatrix 0.4.6

Repeat speech can reuse the validated offline model for up to 60 idle seconds. Six hosted Mac repeat pairs showed a median 1.69-second / 9.9% reduction; matched audio was identical. This small sample is not an iPhone speed guarantee. First requests and requests after release still pay startup cost. Model retention uses additional idle memory.

Memory pressure, backgrounding, cancellation, errors, conversion and audio effects release the model as appropriate. Synthesis settings and reference validation are unchanged. No stock voices or private audio are bundled.

The suggestions screen explains the configured quiet daily owner-account review/build route. Submission remains explicitly public on GitHub; nothing private is automatically attached. A scheduled attempt is recorded but its execution result is unavailable.

Native speech, conversion, packaging, lifecycle and simulator workflow checks passed, including imported reference playback after relaunch. This release promotes the exact verified candidate IPA.

Replace the existing VoiceMatrix app in Strata and keep its data container; do not delete it first. Physical iPhone speed, memory/thermal behavior, update handoff and individual character likeness remain unverified.
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
        (42632930303, CANDIDATE),
        (42642950816, TESTED),
        (42632525550, "1430adbe6b45d2cb4d6c63722beff91b517221a8"),
        (42632525432, "1430adbe6b45d2cb4d6c63722beff91b517221a8"),
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
    report = verify(ROOT / "ipa", ROOT / "speech", ROOT / "conversion", CANDIDATE, VERSION)
    assert report["ipaSHA256"] == "27cc1a45d92529bf1acd5f3c1383f8e278fb990cd6114baa3df3b1bef0c17aef"
    assert report["ipaBytes"] == 731114673
    proof = json.loads((ROOT / "ipa/source-proof.json").read_text())
    for path, expected in proof["files"].items():
        content = subprocess.check_output(["git", "show", f"{TESTED}:{path}"])
        assert hashlib.sha256(content).hexdigest() == expected, f"Shipped app differs from tested source: {path}"
        assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() == expected, f"Merged app differs from candidate: {path}"
    report.update(publicationSource=source, candidateRun=42632930303, workflowRun=int(os.environ["GITHUB_RUN_ID"]), playbackTestSource=TESTED,
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
           "--repo", REPO, "--target", source, "--title", "VoiceMatrix 0.4.6 — faster repeat speech",
           "--notes-file", str(notes))
    published = ROOT / "published"
    published.mkdir(exist_ok=True)
    gh("release", "download", TAG, "--repo", REPO, "-p", IPA, "-D", str(published), "--clobber")
    assert digest(published / IPA) == report["ipaSHA256"], "Published bytes differ from verified IPA"
    dependency = json.loads((ROOT / "ipa/dependency-notices.json").read_text())["proof"]
    inspect_ipa(published / IPA, dependency_proof=dependency, expected_version=VERSION)
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{IPA}"
    description = "Faster repeat offline speech through bounded model reuse. Hosted Mac median 9.9% saving with identical paired audio; iPhone speed and memory remain unverified. Explicit public suggestions and existing private voice storage preserved. No stock voices."
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
        payload = dict(message="Publish verified VoiceMatrix 0.4.6 update feed", branch="main", sha=current["sha"],
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
