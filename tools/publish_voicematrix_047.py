"""Publish only the 0.4.7 IPA whose native gates and playback source have passed."""
import base64, datetime, hashlib, json, os, pathlib, shutil, subprocess, time
from tools.verify_character_kit import verify
from tools.character_package import inspect_ipa
from tools.character_evidence import digest
from tools.sync_verified_release_feeds import updated

REPO = "R347H4CK3R/Ghostline"
VERSION = "0.4.7"
TAG = "voicematrix-v0.4.7"
IPA = "VoiceMatrix-0.4.7.ipa"
TESTED = "ab84585377c5464d70736e629acb6f9b8870a81f"
CANDIDATE = "cff6190170a1ee64a4af86e7eb30db15cf2422be"
ROOT = pathlib.Path("release-evidence")
NOTES = """VoiceMatrix 0.4.7

Open Voices → Manage your collection → Live sync log to see what is happening during voice synchronization: request sent, confirmed laptop receipt, collection checking, file transfer, hash validation and successful offline saving. The timer distinguishes waiting from evidence of progress. Up-to-date, deferred, stopped and failed states are explicit.

The private laptop companion also provides an authenticated live activity page. Laptop file responses do not prove the phone has imported them or that voice training/processing is finished. Older companions remain compatible, with response-only receipt confirmation when detailed activity is unavailable.

Logs are bounded and memory-only. No voice names, paths, recordings, transcripts or credentials are included. Existing imported voices, reference safeguards, saved audio, shared models and synthesis settings are preserved; no private or stock profiles are bundled.

This release promotes the exact candidate checked by native speech, conversion, private import, iPhone SDK typecheck and simulator workflow gates. The companion was verified on Windows with an actual 121-file transfer, unchanged private master and anonymous access rejection. Physical iPhone synchronization and character likeness remain unverified.

Replace the existing VoiceMatrix app in Strata and keep its data container; do not delete it first.
"""

def gh(*args, check=True):
    return subprocess.run(["gh", *args], check=check, capture_output=True, text=True).stdout

def api(path):
    return json.loads(gh("api", path))

def version_key(entry):
    version = tuple(int(x) for x in entry["version"].split("."))
    return (version + (0,) * (4 - len(version)), int(entry.get("buildVersion", "0")))

def validate_tag_target(tagged_object, source):
    assert tagged_object is None or (tagged_object.get("type") == "commit" and tagged_object.get("sha") == source), "Existing release tag targets another source; no publication performed"

def preflight_release_tag(source):
    result = subprocess.run(["gh", "api", f"repos/{REPO}/git/ref/tags/{TAG}"], capture_output=True, text=True)
    if result.returncode:
        error = json.loads(result.stdout)
        assert str(error.get("status")) == "404" and error.get("message") == "Not Found", "Could not verify existing tag; no publication performed"
        validate_tag_target(None, source)
    else:
        validate_tag_target(json.loads(result.stdout)["object"], source)

def validate_published_release(release, tagged_object, source, report):
    assert release["tag_name"] == TAG and not release["draft"] and not release["prerelease"] and release.get("published_at"), "Release is not public and complete"
    assert tagged_object.get("type") == "commit" and tagged_object.get("sha") == source, "Release tag does not target this publication source"
    required = (IPA, IPA + ".sha256", "character-release-verification.json", "dependency-notices.json", "speech-evidence.json", "conversion-result.json")
    for name in required:
        matches = [asset for asset in release["assets"] if asset["name"] == name]
        assert len(matches) == 1 and matches[0]["size"] > 0, "Missing or conflicting published evidence: " + name
    asset = next(asset for asset in release["assets"] if asset["name"] == IPA)
    assert asset["size"] == report["ipaBytes"] and asset.get("digest") == "sha256:" + report["ipaSHA256"], "Published IPA identity differs"

def publication_feed(feed, entry, description):
    result = updated(feed, entry)
    if result != feed:
        app = next(a for a in result["apps"] if a["bundleIdentifier"] == "com.voicematrix.app")
        app["name"] = "VoiceMatrix"
        app["localizedDescription"] = description
    return result

def wait_for_gates():
    # The publication job depends on actual speech/conversion/package jobs.
    # Also bind the already-passed playback/updater tests to every shipped app source.
    for run_id, tested_sha in (
        (43126844268, CANDIDATE),
        (43129173637, TESTED),
        (43126843984, "cff6190170a1ee64a4af86e7eb30db15cf2422be"),
        (43126843938, "cff6190170a1ee64a4af86e7eb30db15cf2422be"),
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

def main():
    source = os.environ["GITHUB_SHA"]
    assert os.environ["GITHUB_REPOSITORY"] == REPO
    wait_for_gates()
    subprocess.run(["git", "fetch", "--depth=1", "origin", TESTED], check=True)
    report = verify(ROOT / "ipa", ROOT / "speech", ROOT / "conversion", CANDIDATE, VERSION)
    assert report["ipaSHA256"] == "590eff59107e555076418c80682f1a3be823ba4b461b5d85ff8c4129cf25fb29"
    assert report["ipaBytes"] == 731161976
    candidate = json.loads((ROOT / "candidate/candidate-verification.json").read_text())
    assert candidate["status"] == "candidate-verified-not-published" and candidate["workflowRun"] == 43126844268
    for key in ("sourceCommit", "inferenceSourceFingerprint", "ipaSHA256", "ipaBytes"):
        assert candidate[key] == report[key], "Candidate artifact verification differs: " + key
    proof = json.loads((ROOT / "ipa/source-proof.json").read_text())
    for path, expected in proof["files"].items():
        content = subprocess.check_output(["git", "show", f"{TESTED}:{path}"])
        assert hashlib.sha256(content).hexdigest() == expected, f"Shipped app differs from tested source: {path}"
        assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() == expected, f"Merged app differs from candidate: {path}"
    report.update(publicationSource=source, candidateRun=43126844268, workflowRun=int(os.environ["GITHUB_RUN_ID"]), playbackTestSource=TESTED,
                  playbackAndUpdaterSimulatorTestsPassed=True)
    verification = ROOT / "character-release-verification.json"
    verification.write_text(json.dumps(report, indent=2) + "\n")
    public_ipa = ROOT / IPA
    shutil.copyfile(ROOT / f"ipa/VoiceMatrix-{VERSION}-character-test.ipa", public_ipa)
    notes = ROOT / "release-notes.txt"
    notes.write_text(NOTES)
    checksum = ROOT / (IPA + ".sha256")
    checksum.write_text(report["ipaSHA256"] + "  " + IPA + "\n")
    preflight_release_tag(source)
    existing = gh("release", "view", TAG, "--repo", REPO, "--json", "tagName", check=False)
    if not existing:
        gh("release", "create", TAG, str(public_ipa), str(checksum), str(verification),
           str(ROOT / "ipa/dependency-notices.json"),
           str(ROOT / "speech/speech-evidence.json"),
           str(ROOT / "conversion/conversion-evidence/conversion-result.json"),
           "--repo", REPO, "--target", source, "--title", "VoiceMatrix 0.4.7 — live voice sync log",
           "--notes-file", str(notes))
    published = ROOT / "published"
    published.mkdir(exist_ok=True)
    release = api(f"repos/{REPO}/releases/tags/{TAG}")
    tagged = api(f"repos/{REPO}/git/ref/tags/{TAG}")["object"]
    validate_published_release(release, tagged, source, report)
    expected_assets = {
        IPA: public_ipa,
        IPA + ".sha256": checksum,
        "character-release-verification.json": verification,
        "dependency-notices.json": ROOT / "ipa/dependency-notices.json",
        "speech-evidence.json": ROOT / "speech/speech-evidence.json",
        "conversion-result.json": ROOT / "conversion/conversion-evidence/conversion-result.json",
    }
    for name, expected in expected_assets.items():
        gh("release", "download", TAG, "--repo", REPO, "-p", name, "-D", str(published), "--clobber")
        assert digest(published / name) == digest(expected), "Published evidence differs: " + name
    assert digest(published / IPA) == report["ipaSHA256"], "Published bytes differ from verified IPA"
    dependency = json.loads((ROOT / "ipa/dependency-notices.json").read_text())["proof"]
    inspect_ipa(published / IPA, dependency_proof=dependency, expected_version=VERSION)
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{IPA}"
    description = "Live private voice sync activity: laptop receipt and checking, download progress, validation and saved completion. Explicit stop, failure and up-to-date states. Existing private voices/audio and offline engines preserved; no stock voices. Physical iPhone sync remains unverified."
    entry = dict(version=VERSION, buildVersion="1", date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                 downloadURL=url, localizedDescription=description, minOSVersion="26.0",
                 size=report["ipaBytes"], sha256=report["ipaSHA256"])
    feeds = {}
    for name in ("livecontainer-test.json", "source.json", "strata-source.json"):
        current = api(f"repos/{REPO}/contents/{name}?ref=main")
        feed = json.loads(base64.b64decode(current["content"]))
        next_feed = publication_feed(feed, entry, description)
        if next_feed == feed:
            feeds[name] = "already current or newer release preserved"
            continue
        feed = next_feed
        expected_versions = next(x for x in feed["apps"] if x["bundleIdentifier"] == "com.voicematrix.app")["versions"]
        payload = dict(message="Publish verified VoiceMatrix 0.4.7 update feed", branch="main", sha=current["sha"],
                       content=base64.b64encode((json.dumps(feed, indent=2) + "\n").encode()).decode())
        request = ROOT / ("feed-" + name)
        request.write_text(json.dumps(payload))
        gh("api", "--method", "PUT", f"repos/{REPO}/contents/{name}", "--input", str(request))
        fresh = api(f"repos/{REPO}/contents/{name}?ref=main")
        actual = next(x for x in json.loads(base64.b64decode(fresh["content"]))["apps"] if x["bundleIdentifier"] == "com.voicematrix.app")
        assert actual["versions"] == expected_versions
        feeds[name] = "published and read back"
    report.update(status="published-and-redownload-verified", url=url, tag=TAG, feeds=feeds)
    (ROOT / "publication-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
