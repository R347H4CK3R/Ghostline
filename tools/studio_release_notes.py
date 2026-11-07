"""Write release notes from validated evidence and the actual approved IPA."""
import hashlib,json,pathlib,sys,zipfile
summary=json.loads(pathlib.Path(sys.argv[1]).read_text());ipa=pathlib.Path(sys.argv[2])
with zipfile.ZipFile(ipa) as z:lock=json.loads(z.read('Payload/VoiceMatrix.app/Phonon/manifest.json'))
count=len(lock['voices'])
assert count==summary['approvedProfiles'] and count>=500
nc=sum(bool(v.get('usageRestriction')) for v in lock['voices'])
with ipa.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
rows='\n'.join('| '+name+' | '+str(n)+' |' for name,n in summary['categories'].items())
text=f"""# VoiceMatrix 0.3.0 experimental

{count} included neural conditioning profiles, with shared offline Phonon speech and OpenVoice V2 speech-to-speech conversion. {sum(v['engine']=='phonon31m' for v in lock['voices'])} profiles use Phonon directly; {sum(v['engine']=='phonon31m-openvoicev2' for v in lock['voices'])} use the shared converter to render consented or licensed reference-derived voices from a bundled Phonon base. Every included profile passed the matched native audio and independent English-transcription gates on all required clips. The full candidate checks and exclusions are included as release assets.

Choose a voice, type and Speak, then Listen, Save or Share a valid WAV. Change My Voice supports microphone recording or imported audio up to 10 seconds, selection, neural conversion, playback and WAV export. Longer typed messages are generated in bounded chunks. Conversion preserves duration within the implemented test tolerance; this is not a real-time microphone effect.

Search, favorites, recent voices and overlapping categories include everyday, character styles and measured vocal-depth groups. A profile appears in several applicable categories but counts once.

| Category | Profiles |
|---|---:|
{rows}

All runtime models, token/profile assets, attribution and license notices are bundled. No runtime downloads, login, hosted inference, API key or silent system-voice fallback. {nc} profiles have noncommercial-only reference terms and display a restriction in the voice picker. Refer to bundled notices for each source.

Native tests use an iOS simulator, including every profile's speech and conversion outputs, varied English for additions, decoding, cancellation, navigation and recording/playback ownership. Independent whisper.cpp transcription uses no reference prompt or constrained vocabulary, a <=10% word-error gate, non-silence and no full-scale samples. Exact model/source hashes, every attempt and inference fingerprints are retained.

These checks establish automated functionality and short-clip intelligibility. Human naturalness, perceptual distinctness, intended character resemblance and near-indistinguishable quality remain unverified. Numerical speaker conditioning and different source recordings do not establish listener-perceived similarity. No authorized recognizable likeness models are claimed. Physical per-profile verification: 0 recorded; controlled listening verification: 0. Simulator memory samples are not iPhone peak memory. The previous working 0.2.2 release is preserved.

Unsigned ARM64, bundle identifier com.voicematrix.app, version 0.3.0 build 5, iOS 26+. IPA bytes: {ipa.stat().st_size}. SHA-256: {digest}. The release workflow separately downloads the published archive and repeats SHA, archive, icon, model, profile and inference-evidence checks; see release-verification.json for the result.
"""
pathlib.Path('RELEASE-NOTES-0.3.0.md').write_text(text)
print(text)
