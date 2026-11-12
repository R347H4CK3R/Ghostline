"""Publish only the 0.4.9 IPA whose native gates and playback source have passed."""
import base64, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, time
from tools.verify_character_kit import verify
from tools.character_package import inspect_ipa
from tools.character_evidence import digest
from tools.sync_verified_release_feeds import updated

REPO = "R347H4CK3R/Ghostline"
VERSION = "0.4.9"
BUILD = "2"
TAG = "voicematrix-v0.4.9-build2"
IPA = "VoiceMatrix-0.4.9-build2.ipa"
# Bound to the fresh 0.4.9 candidate evidence. Every gate is rechecked before
# any publication; no previous release evidence can satisfy these bindings.
CANDIDATE = '1ea3e3930ea0aa052df2815365ebb244e7179c83'
EXPECTED_IPA_SHA256 = '0457d3aeb8a38199d327db0f1f0206b7c4fa352618b63bfe6f9a54ea85af5ffd'
EXPECTED_IPA_BYTES = 1305715123
REQUIRED_GATES = (
    ".github/workflows/voicematrix-049-candidate.yml",
    ".github/workflows/character-ui-smoke.yml",
    ".github/workflows/native-app.yml",
    ".github/workflows/native-queue.yml",
    ".github/workflows/native-character-folder.yml",
    ".github/workflows/video-workflow.yml",
    ".github/workflows/queue-processor.yml",
    ".github/workflows/queue-recovery.yml",
)
GATES = dict(zip(REQUIRED_GATES, [43318433986,43318434113,43318433962,43318433772,43318433839,43318434138,43318433646,43318433817]))

ROOT = pathlib.Path("release-evidence")
NOTES = """VoiceMatrix 0.4.9 build 2 — standalone local-studio test

This is a test update, not finished 1.0.0. Local media and supported authorized direct-media links can be processed inside the app without a laptop: bundled speaker analysis, local transcription, reference-conditioned preview, word checks and automatic reference-profile import. Complete retained logs distinguish actual work from screen refresh. Previous voices and source files are retained.

The exact-source Apple Silicon production-coordinator test used synthetic neutral speech with networking denied. It verified cancellation/resume, source retention, prior-profile preservation, new profile import/reload and generated speech. Native iOS simulator UI/import and ARM64 package gates also passed. These are not physical iPhone tests. Character identity/likeness, broad video-site acquisition, music separation and RVC training are not verified. Profiles are accurately labeled unidentified/reference-only; no claim of indistinguishable voices.

Install with SideStore over the existing app and keep its data. On-device performance and the complete imported-media workflow still require your iPhone test. Keep the app open during processing; background interruption retains work for Resume.
"""


def validate_binding(candidate, gates, ipa_sha256, ipa_bytes):
    assert isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{40}", candidate) and candidate != "0" * 40, "Unbound candidate source; no publication performed"
    assert set(gates) == set(REQUIRED_GATES), "Unbound required gates; no publication performed"
    assert all(type(value) is int and value > 0 for value in gates.values()) and len(set(gates.values())) == len(REQUIRED_GATES), "Unbound or duplicate gate runs; no publication performed"
    assert isinstance(ipa_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", ipa_sha256) and ipa_sha256 != "0" * 64, "Unbound IPA hash; no publication performed"
    assert type(ipa_bytes) is int and ipa_bytes > 0, "Unbound IPA size; no publication performed"


def validate_gate(run, source, workflow):
    assert run["head_sha"] == source, "Required gate tested another source"
    assert run["path"] == workflow, "Required gate used another workflow"
    assert run["repository"]["full_name"] == REPO, "Required gate belongs to another repository"
    assert run["event"] in ("push", "workflow_dispatch"), "Required gate is not a direct source run"
    assert run["status"] == "completed" and run["conclusion"] == "success", "Required gate has not succeeded"


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
    assert release["tag_name"] == TAG and not release["draft"] and release["prerelease"] is True and release.get("published_at"), "Release is not public and complete"
    assert tagged_object.get("type") == "commit" and tagged_object.get("sha") == source, "Release tag does not target this publication source"
    required = (IPA, IPA + ".sha256", "character-release-verification.json", "dependency-notices.json", "speech-evidence.json", "conversion-result.json", "pipeline-evidence.json")
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
    validate_binding(CANDIDATE, GATES, EXPECTED_IPA_SHA256, EXPECTED_IPA_BYTES)
    for workflow, run_id in GATES.items():
        deadline = time.monotonic() + 1200
        while True:
            run = api(f"repos/{REPO}/actions/runs/{run_id}")
            if run["status"] == "completed":
                validate_gate(run, CANDIDATE, workflow)
                break
            assert run["head_sha"] == CANDIDATE and run["path"] == workflow, "Pending gate identity differs"
            assert time.monotonic() < deadline, f"Required check still pending: {run_id}"
            time.sleep(20)


def main():
    source = os.environ["GITHUB_SHA"]
    assert os.environ["GITHUB_REPOSITORY"] == REPO
    wait_for_gates()
    subprocess.run(["git", "fetch", "--depth=1", "origin", CANDIDATE], check=True)
    report = verify(ROOT / "ipa", ROOT / "speech", ROOT / "conversion", CANDIDATE, VERSION, expected_build=BUILD)
    assert report["ipaSHA256"] == EXPECTED_IPA_SHA256
    assert report["ipaBytes"] == EXPECTED_IPA_BYTES
    candidate = json.loads((ROOT / "candidate/candidate-verification.json").read_text())
    assert candidate["status"] == "candidate-verified-not-published" and candidate["workflowRun"] == GATES[REQUIRED_GATES[0]]
    for key in ("sourceCommit", "inferenceSourceFingerprint", "ipaSHA256", "ipaBytes"):
        assert candidate[key] == report[key], "Candidate artifact verification differs: " + key
    pipeline = json.loads((ROOT / "local-pipeline/pipeline-evidence.json").read_text())
    assert pipeline['sourceCommit'] == CANDIDATE
    assert all(pipeline[key] is True for key in ('cancellationRetainedSource','freshStoreReloadPreservedIDs','priorProfilePreserved','resumeCompleted'))
    assert pipeline['sourceRetainedSHA256'] == pipeline['fixtureSHA256']
    assert pipeline['importedIDs'] and pipeline['newSpeechWordErrorRate'] <= .1
    assert pipeline['physicalIPhoneVerified'] is False and pipeline['likenessVerified'] is False
    proof = json.loads((ROOT / "ipa/source-proof.json").read_text())
    for path, expected in proof["files"].items():
        content = subprocess.check_output(["git", "show", f"{CANDIDATE}:{path}"])
        assert hashlib.sha256(content).hexdigest() == expected, f"Shipped app differs from tested source: {path}"
        assert hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() == expected, f"Merged app differs from candidate: {path}"
    report.update(publicationSource=source, candidateRun=GATES[REQUIRED_GATES[0]], workflowRun=int(os.environ["GITHUB_RUN_ID"]), playbackTestSource=CANDIDATE,
                  playbackAndUpdaterSimulatorTestsPassed=True, workflowNativeAndBrowserTestsPassed=True, requiredGateRuns=GATES, standaloneCoordinatorPassed=True, buildVersion=BUILD)
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
           str(ROOT / "local-pipeline/pipeline-evidence.json"),
           "--repo", REPO, "--target", source, "--prerelease", "--title", "VoiceMatrix 0.4.9 build 2 — standalone test",
           "--notes-file", str(notes))
    published = ROOT / "published"
    published.mkdir(exist_ok=True)
    release = api(f"repos/{REPO}/releases/tags/{TAG}")
    tagged = api(f"repos/{REPO}/git/ref/tags/{TAG}")["object"]
    validate_published_release(release, tagged, source, report)
    expected_assets = {
        "pipeline-evidence.json": ROOT / "local-pipeline/pipeline-evidence.json",
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
    inspect_ipa(published / IPA, dependency_proof=dependency, expected_version=VERSION, expected_build=BUILD)
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{IPA}"
    description = "Standalone local-studio test: bundled speaker analysis, transcription, reference preview, automatic import and retained live logs. No laptop required for this path. Tested with synthetic neutral speech on Apple Silicon and iOS simulator; physical iPhone behavior, character likeness, broad video-site support and RVC training remain unverified. Not finished 1.0.0. Existing voices and source media retained."
    entry = dict(version=VERSION, buildVersion=BUILD, date=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
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
        payload = dict(message="Publish verified VoiceMatrix 0.4.9 update feed", branch="main", sha=current["sha"],
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
