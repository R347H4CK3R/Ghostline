import Foundation
import AVFoundation
import Combine
import CryptoKit

@MainActor final class LocalVideoStudio: ObservableObject {
    struct Event: Codable, Identifiable { let id: UUID; let time: Date; let stage: String; let message: String }
    struct Job: Codable, Identifiable {
        let id: UUID
        let created: Date
        var updated: Date
        var stage: String
        var message: String
        var originalAcquisitionURL: URL?
        var acquisitionURL: URL?
        var sourceFile: String?
        var sourceSHA256: String?
        var analysisFile: String?
        var analysisSHA256: String?
        var referenceFile: String?
        var previewFile: String?
        var voiceID: String?
        var speakerVoiceIDs: [String:String]?
        var speakerOutcomes: [String:String]?
        var qualityPolicyVersions: [String:Int]?
        var completed = false
        var events: [Event] = []
    }
    @Published private(set) var current: Job?
    @Published private(set) var history: [Job] = []
    @Published private(set) var busy = false
    @Published private(set) var notice = "Import an authorized local video or recording. Processing runs on this iPhone. URL acquisition contacts only the source website."
    private let root: URL
    private let transcriber = OnDeviceTranscription()
    private let engine = F5ReferenceEngine(idleRetention: .zero)
    private var operation: Task<Void, Never>?
    private var active = true
    private var runToken = UUID()
    private let previewText = "I found a strange device near the portal."
    init() {
        root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("LocalVideoStudio", isDirectory: true)
        reloadHistory()
        current = history.first
        if current?.completed == false { notice = "Previous work was retained. Resume to continue while this app is open." }
    }
    var reference: URL? { current?.referenceFile.map { folder.appendingPathComponent($0) } }
    var preview: URL? { current?.previewFile.map { folder.appendingPathComponent($0) } }
    private var folder: URL { root.appendingPathComponent(current!.id.uuidString.lowercased(), isDirectory: true) }
    private static func hash(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    private func reloadHistory() {
        history = ((try? FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)) ?? []).compactMap { url in
            guard UUID(uuidString: url.lastPathComponent) != nil,
                  let values = try? url.appendingPathComponent("job.json").resourceValues(forKeys: [.fileSizeKey, .isSymbolicLinkKey]),
                  values.isSymbolicLink != true, (values.fileSize ?? Int.max) <= 262_144,
                  let data = try? Data(contentsOf: url.appendingPathComponent("job.json")),
                  let job = try? JSONDecoder().decode(Job.self, from: data), job.id.uuidString.lowercased() == url.lastPathComponent else { return nil }
            func safe(_ value: String?) -> Bool { value == nil || (value!.range(of: "^[a-zA-Z0-9_-]+(?:\\.[a-zA-Z0-9_-]+)*$", options: .regularExpression) != nil) }
            guard safe(job.sourceFile), safe(job.analysisFile), safe(job.referenceFile), safe(job.previewFile) else { return nil }
            if let input = job.acquisitionURL, (try? LocalMediaURLPolicy.input(input.absoluteString)) == nil { return nil }
            return job
        }.sorted { $0.created > $1.created }
    }
    private func update(_ stage: String, _ text: String, log: Bool = true) throws {
        guard var value = current else { return }
        value.updated = Date(); value.stage = stage; value.message = text
        if log { value.events.append(Event(id: UUID(), time: value.updated, stage: stage, message: text)); value.events = Array(value.events.suffix(160)) }
        try JSONEncoder().encode(value).write(to: folder.appendingPathComponent("job.json"), options: .atomic)
        current = value; notice = text
    }
    func selectHistory(_ job: Job) { guard !busy else { return }; current = job; notice = job.message }
    func setActive(_ value: Bool) { active = value; if !value, busy { cancel() } }
    func memoryWarning() {
        guard busy else { return }
        operation?.cancel()
        try? update("Stopping for memory", "iOS reported memory pressure. Stopping at a safe boundary and retaining source/output files.")
    }
    func thermalChanged() {
        guard busy, ProcessInfo.processInfo.thermalState == .serious || ProcessInfo.processInfo.thermalState == .critical else { return }
        operation?.cancel()
        try? update("Stopping for temperature", "iPhone temperature is high. Let it cool before resuming; retained files are kept.")
    }
    func cancel() { guard busy else { return }; operation?.cancel(); try? update("Stopping", "Stopping at a safe boundary. Source and completed outputs are retained.") }
    func startURL(_ text: String, authorized: Bool, library: CharacterLibrary, audio: AudioStore, speech: SpeechStudio) {
        do {
            _ = try LocalMediaURLPolicy.input(text)
            guard let original = URL(string: text.trimmingCharacters(in: .whitespacesAndNewlines)) else { throw LocalMediaURLPolicy.Failure.url }
            start(original, authorized: authorized, library: library, audio: audio, speech: speech)
        }
        catch { notice = LocalMediaURLPolicy.Failure.url.errorDescription! }
    }
    func start(_ source: URL, authorized: Bool, library: CharacterLibrary, audio: AudioStore, speech: SpeechStudio) {
        guard authorized, !busy, active else { return }
        guard !audio.processingInUse, !audio.microphoneInUse else { notice = "Stop the other recording or speech job first."; return }
        do {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            let free = try root.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage ?? 0
            let retained = try LocalMediaAcquisition.retainedBytes(root: root)
            guard free >= 800_000_000, retained < 2_000_000_000 else { throw LocalError.storage }
            let now = Date()
            current = Job(id: UUID(), created: now, updated: now, stage: "Received", message: "Source selected; preparing retained acquisition.")
            if !source.isFileURL { current?.acquisitionURL = try LocalMediaURLPolicy.input(source.absoluteString); current?.originalAcquisitionURL = source }
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
            try update("Received", source.isFileURL ? "App received the selected local media. Nothing is uploaded." : "App received the URL. Downloading directly from its website; no laptop or conversion service. The private URL is not shown in this log.")
            run(source: source.isFileURL ? source : nil, library: library, audio: audio, speech: speech)
        } catch { notice = "Could not start a local job. Check free storage; existing voices were kept." }
    }
    func resume(library: CharacterLibrary, audio: AudioStore, speech: SpeechStudio) {
        guard !busy, active, let job = current, !job.completed, job.sourceFile != nil || job.acquisitionURL != nil else { return }
        run(source: nil, library: library, audio: audio, speech: speech)
    }
    private enum LocalError: LocalizedError {
        case storage, source, candidate, preview, engine, thermal
        var errorDescription: String? {
            switch self {
            case .storage: return "Free at least 800 MB. Retained local jobs have a 2 GB admission limit; no old files were deleted."
            case .source: return "The retained source is missing, changed or unsupported. Existing voices were kept."
            case .candidate: return "No acceptable reference was found. Speaker timing is not proof of music-free speech or character identity."
            case .preview: return "Three previews failed the spoken-word check. References and completed previews were retained for review."
            case .engine: return "The bundled F5 engine is unavailable. A complete app build is required; no network fallback was used."
            case .thermal: return "iPhone temperature is too high for this job. Let it cool, then Resume."
            }
        }
    }
    private func check() throws {
        try Task.checkCancellation()
        if ProcessInfo.processInfo.thermalState == .serious || ProcessInfo.processInfo.thermalState == .critical { throw LocalError.thermal }
    }
    private func run(source: URL?, library: CharacterLibrary, audio: AudioStore, speech: SpeechStudio) {
        guard let lease = audio.claimProcessing() else { notice = "Stop the other recording or speech job first."; return }
        busy = true
        let run = UUID(); runToken = run
        let jobFolder = folder
        operation = Task {
            var libraryOwner: UUID?
            defer { if let libraryOwner { library.endLocalGeneration(libraryOwner) }; busy = false; audio.releaseProcessing(lease); reloadHistory() }
            do {
                try check()
                libraryOwner = try await library.beginLocalGeneration()
                if current?.sourceFile == nil, let input = current?.acquisitionURL {
                    try update("Acquiring source", "Preparing a bounded direct website download. Partial files and completed tracks remain retained.")
                    let result = try await LocalMediaAcquisition.acquire(input: input, folder: jobFolder) { [weak self] message in
                        Task { @MainActor in
                            guard let self, self.runToken == run, self.busy, self.current?.stage == "Acquiring source" else { return }
                            try? self.update("Acquiring source", message, log: !message.hasPrefix("Received ") && !message.hasPrefix("Merging tracks:"))
                        }
                    }
                    try check()
                    current?.sourceFile = result.file; current?.sourceSHA256 = result.sha256
                    try update("Source retained", "Downloaded source and any original separate tracks are retained. Processing now stays entirely on this iPhone.")
                }
                if let source {
                    let access = source.startAccessingSecurityScopedResource()
                    defer { if access { source.stopAccessingSecurityScopedResource() } }
                    let ext = source.pathExtension.lowercased()
                    guard ["mp4", "mov", "m4v", "wav", "m4a", "aac", "caf"].contains(ext) else { throw LocalError.source }
                    let destination = jobFolder.appendingPathComponent("source." + ext)
                    try update("Copying source", "Keeping a private source copy for recovery.")
                    let copy = Task.detached { () throws -> String in
                        let v = try source.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
                        guard v.isRegularFile == true, v.isSymbolicLink != true, let size = v.fileSize, size > 0, size <= 536_870_912 else { throw LocalError.source }
                        guard FileManager.default.createFile(atPath: destination.path, contents: nil) else { throw LocalError.storage }
                        let input = try FileHandle(forReadingFrom: source), output = try FileHandle(forWritingTo: destination)
                        defer { try? input.close(); try? output.close() }
                        var hash = SHA256(), count = 0
                        var lastNotice = Date()
                        while let bytes = try input.read(upToCount: 1_048_576), !bytes.isEmpty {
                            try Task.checkCancellation(); count += bytes.count
                            guard count <= size else { throw LocalError.source }
                            try output.write(contentsOf: bytes); hash.update(data: bytes)
                            if Date().timeIntervalSince(lastNotice) >= 1 {
                                lastNotice = Date(); let copied = count
                                Task { @MainActor [weak self] in
                                    guard let self, self.runToken == run, self.busy, self.current?.stage == "Copying source" else { return }
                                    try? self.update("Copying source", "Copied \(copied) of \(size) bytes into retained app storage.", log: false)
                                }
                            }
                        }
                        guard count == size else { throw LocalError.source }
                        try output.synchronize()
                        return hash.finalize().map { String(format: "%02x", $0) }.joined()
                    }
                    let digest = try await withTaskCancellationHandler { try await copy.value } onCancel: { copy.cancel() }
                    current?.sourceFile = destination.lastPathComponent; current?.sourceSHA256 = digest
                    try update("Source retained", "Private source copy committed. It will not be deleted automatically.")
                }
                guard let name = current?.sourceFile, let expectedHash = current?.sourceSHA256 else { throw LocalError.source }
                let retained = jobFolder.appendingPathComponent(name)
                let digestTask = Task.detached { () throws -> String in
                    let handle = try FileHandle(forReadingFrom: retained); defer { try? handle.close() }
                    var hash = SHA256()
                    while let bytes = try handle.read(upToCount: 1_048_576), !bytes.isEmpty { try Task.checkCancellation(); hash.update(data: bytes) }
                    return hash.finalize().map { String(format: "%02x", $0) }.joined()
                }
                let actualHash = try await withTaskCancellationHandler { try await digestTask.value } onCancel: { digestTask.cancel() }
                guard expectedHash == actualHash else { throw LocalError.source }
                try update("Checking local transcription", "Checking the bundled Parakeet speech recognizer. No OS speech assets or server recognition are used.")
                try await transcriber.authorize()
                await speech.releaseModelsForCharacter()
                await engine.finishRequest(keepWarm: false)
                let analysis: LocalSpeakerDiarization.Analysis
                if let name = current?.analysisFile, let digest = current?.analysisSHA256 {
                    let url = jobFolder.appendingPathComponent(name)
                    let v = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
                    guard v.isRegularFile == true, v.isSymbolicLink != true, (v.fileSize ?? Int.max) <= 4_000_000 else { throw LocalError.source }
                    let data = try Data(contentsOf: url)
                    guard Self.hash(data) == digest else { throw LocalError.source }
                    analysis = try JSONDecoder().decode(LocalSpeakerDiarization.Analysis.self, from: data)
                    try LocalSpeakerDiarization.validate(analysis)
                    try update("Speaker analysis retained", "Reusing the verified retained analysis so speaker groups stay consistent across Resume.")
                } else {
                    try update("Analyzing speakers", "Loading bundled speaker analysis. Speaker groups are not character identities.")
                    analysis = try await LocalSpeakerDiarization.analyze(source: retained) { [weak self] message in
                        Task { @MainActor in
                            guard let self, self.runToken == run, self.busy, self.current?.stage == "Analyzing speakers" else { return }
                            try? self.update("Analyzing speakers", message, log: false)
                        }
                    }
                    try check()
                    let data = try JSONEncoder().encode(analysis)
                    let name = "diarization-" + UUID().uuidString.lowercased() + ".json"
                    try data.write(to: jobFolder.appendingPathComponent(name), options: .atomic)
                    current?.analysisFile = name; current?.analysisSHA256 = Self.hash(data)
                    try update("Speaker analysis retained", "Saved the source-bound speaker analysis before creating references.")
                }
                let groups = analysis.speakerWindows
                guard !groups.isEmpty else { throw LocalError.candidate }
                try update("Speaker groups found", "Found \(groups.count) tentative speaker groups. Detected overlaps are excluded; music separation and character names are not verified.")
                guard let bundle = Bundle.main.url(forResource: "F5TTS", withExtension: nil) else { throw LocalError.engine }
                if current?.speakerVoiceIDs == nil { current?.speakerVoiceIDs = [:] }
                if current?.speakerOutcomes == nil { current?.speakerOutcomes = [:] }
                if current?.qualityPolicyVersions == nil { current?.qualityPolicyVersions = [:] }
                var saved = 0, unresolved = 0
                for speaker in groups {
                    try check()
                    if current?.qualityPolicyVersions?[speaker.speaker] == LocalSoundQualityPolicy.version, let id = current?.speakerVoiceIDs?[speaker.speaker], let existing = library.profiles.first(where: { $0.id == id }) {
                        saved += 1
                        try update("Reference already saved", "Reused \(existing.name) (ID \(existing.id)). Library now contains \(library.profiles.count) voices; previous voices were kept.")
                        continue
                    }
                    var previews = 0, imported = false
                    for (index, window) in speaker.windows.enumerated() {
                        try check()
                        try update("Selecting reference", "Speaker \(speaker.speaker): checking candidate \(index + 1) of \(speaker.windows.count). Detected overlap was excluded; this is not music separation.")
                        let clip: LocalVideoAudio.Reference
                        do { clip = try await LocalVideoAudio.extract(source: retained, start: window.start, seconds: window.seconds) }
                        catch LocalVideoAudio.Failure.unusableAudio { continue }
                        let attempt = UUID().uuidString.lowercased()
                        let reference = jobFolder.appendingPathComponent("reference-" + attempt + ".wav")
                        try clip.wave.write(to: reference, options: .atomic)
                        current?.referenceFile = reference.lastPathComponent
                        try update("Screening candidate", "Checking speaker \(speaker.speaker) for music, singing and speech evidence on this iPhone.")
                        let quality: LocalSoundQuality.Evidence
                        do {
                            quality = try await LocalSoundQuality.analyze(source: reference) { [weak self] message in
                                Task { @MainActor in
                                    guard let self, self.runToken == run, self.busy, self.current?.stage == "Screening candidate", self.current?.referenceFile == reference.lastPathComponent else { return }
                                    try? self.update("Screening candidate", message, log: false)
                                }
                            }
                        } catch {
                            let failure: [String:Any] = ["schemaVersion":1,"policyVersion":LocalSoundQualityPolicy.version,"sourceSHA256":Self.hash(clip.wave),"status":"Screening did not complete","reason":error.localizedDescription]
                            try? JSONSerialization.data(withJSONObject:failure,options:[.sortedKeys]).write(to:jobFolder.appendingPathComponent("quality-" + attempt + ".json"),options:.atomic)
                            throw error
                        }
                        guard quality.sourceSHA256 == Self.hash(clip.wave) else { throw LocalError.source }
                        try JSONEncoder().encode(quality).write(to:jobFolder.appendingPathComponent("quality-" + attempt + ".json"),options:.atomic)
                        guard quality.decision.admitted else {
                            try update("Candidate needs review", quality.decision.reason)
                            continue
                        }
                        try check()
                        try update("Transcribing reference", "Recognizing this candidate locally. Model-detected overlaps were excluded. Music and character identity are not verified.")
                        let transcript: String
                        do { transcript = try await transcriber.transcribe(reference) { [weak self] in
                            guard let self, self.runToken == run, self.busy, self.current?.stage == "Transcribing reference", self.current?.referenceFile == reference.lastPathComponent else { return }
                            try? self.update("Transcribing reference", "On-device recognition is producing results.", log: false)
                        } }
                        catch OnDeviceTranscription.Failure.noSpeech { continue }
                        guard let transcriptionEvidence = transcriber.lastEvidence,
                              transcriptionEvidence.inputSHA256 == Self.hash(clip.wave) else { throw LocalError.candidate }
                        try JSONEncoder().encode(transcriptionEvidence).write(to: jobFolder.appendingPathComponent("transcription-evidence-" + attempt + ".json"), options: .atomic)
                        try Data(transcript.utf8).write(to: jobFolder.appendingPathComponent("transcript-" + attempt + ".txt"), options: .atomic)
                        try check(); previews += 1
                        try update("Generating preview", "Loading the bundled F5 engine and generating preview \(previews) of at most 3 for speaker \(speaker.speaker). No laptop or server is used.")
                        let preview = jobFolder.appendingPathComponent("preview-" + attempt + ".wav")
                        try await engine.load(localBundle: bundle)
                        try await engine.speak(text: previewText, referenceAudio: reference, referenceText: transcript, destination: preview, preserveIncomplete: true) { [weak self] part, total in
                            Task { @MainActor in guard let self, self.runToken == run, self.busy, self.current?.stage == "Generating preview", self.current?.referenceFile == reference.lastPathComponent else { return }; try? self.update("Generating preview", "Generating speech part \(part) of \(total).", log: false) }
                        }
                        await engine.finishRequest(keepWarm: false)
                        current?.previewFile = preview.lastPathComponent
                        try update("Verifying preview", "Checking the generated words locally. This does not verify likeness.")
                        let recognized: String
                        do { recognized = try await transcriber.transcribe(preview) }
                        catch OnDeviceTranscription.Failure.noSpeech { if previews >= 3 { break }; continue }
                        guard let previewEvidence = transcriber.lastEvidence else { throw LocalError.preview }
                        try JSONEncoder().encode(previewEvidence).write(to: jobFolder.appendingPathComponent("preview-asr-evidence-" + attempt + ".json"), options: .atomic)
                        guard LocalStudioEvidence.wordErrorRate(expected: previewText, actual: recognized) <= 0.1 else {
                            try update("Preview rejected", "Spoken words did not pass. This preview is retained but will not be imported.")
                            if previews >= 3 { break }; continue
                        }
                        try check()
                        if let existing = library.profiles.first(where: { $0.referenceSHA256 == Self.hash(clip.wave) && $0.referenceText == transcript }) {
                            library.selectedID = existing.id
                            current?.voiceID = existing.id
                            current?.speakerVoiceIDs?[speaker.speaker] = existing.id
                            current?.qualityPolicyVersions?[speaker.speaker] = LocalSoundQualityPolicy.version
                            current?.speakerOutcomes?[speaker.speaker] = "Saved reference; word check passed; likeness unverified"
                            imported = true; saved += 1
                            try update("Reference ready", "Reused \(existing.name) (ID \(existing.id)). Library now contains \(library.profiles.count) voices. Preview and screening evidence were retained; likeness is not verified.")
                            break
                        }
                        let id = "local-" + current!.id.uuidString.lowercased() + "-" + speaker.speaker.lowercased()
                        let collection = jobFolder.appendingPathComponent("collection-" + attempt, isDirectory: true)
                        let voiceFolder = collection.appendingPathComponent(id, isDirectory: true)
                        try FileManager.default.createDirectory(at: voiceFolder, withIntermediateDirectories: true)
                        let metadata: [String: Any] = ["id": id, "name": "Unidentified speaker " + speaker.speaker + " " + String(current!.id.uuidString.prefix(6)), "source": "User-authorized local media SHA256 " + expectedHash, "permission": "User affirmed source-use authorization in the local studio", "referenceText": transcript, "schemaVersion": 1, "kind": "f5-reference", "engine": "F5TTS_v1_Base", "referenceFile": "reference.wav", "referenceSHA256": Self.hash(clip.wave), "trainedModel": false, "categories": ["Local", "Unidentified", "Preview-only"], "referenceBytes": clip.wave.count, "seconds": clip.seconds]
                        try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]).write(to: voiceFolder.appendingPathComponent("manifest.json"), options: .atomic)
                        try clip.wave.write(to: voiceFolder.appendingPathComponent("reference.wav"), options: .atomic)
                        try JSONSerialization.data(withJSONObject: ["schemaVersion": 1, "voices": [["id": id, "folder": id]]]).write(to: collection.appendingPathComponent("collection.json"), options: .atomic)
                        try update("Importing", "Atomically validating and registering the preview-only reference on this iPhone.")
                        try await library.importLocalGeneratedCollection(collection, owner: libraryOwner!)
                        guard let savedProfile = library.profiles.first(where: { $0.id == id }) else { throw LocalError.candidate }
                        current?.voiceID = id
                        current?.speakerVoiceIDs?[speaker.speaker] = id
                        current?.qualityPolicyVersions?[speaker.speaker] = LocalSoundQualityPolicy.version
                        current?.speakerOutcomes?[speaker.speaker] = "Saved reference; word check passed; likeness unverified"
                        imported = true; saved += 1
                        try update("Reference ready", "Added \(savedProfile.name) (ID \(savedProfile.id)). Library now contains \(library.profiles.count) voices; previous voices were kept. Screening and word checks passed, but character identity, separation and RVC training are not verified.")
                        break
                    }
                    if !imported {
                        unresolved += 1
                        current?.speakerOutcomes?[speaker.speaker] = "No candidate passed all screening and spoken-word checks"
                        try update("Speaker needs review", "Speaker \(speaker.speaker) has no accepted reference. Sources and attempts were retained; continuing other groups.")
                    }
                }
                current?.completed = saved > 0 && unresolved == 0
                try update(unresolved == 0 ? "Speaker references ready" : "Partial result needs review", "Saved or reused \(saved) speaker references; \(unresolved) groups need review. Likeness, character identity, music separation and RVC training are not verified.")
                return
            } catch {
                await engine.finishRequest(keepWarm: false)
                let canceled = error is CancellationError || Task.isCancelled
                let pauseMessage = current?.acquisitionURL != nil ? "Acquisition or processing paused. Completed tracks and partial attempts are kept. Resume reuses verified completed files; incomplete downloads restart without unsafe byte appending." : current?.sourceFile == nil ? "Source copy interrupted. Partial data was kept; choose the source again to start a new job." : "Paused. Retained source and completed outputs are safe. Resume while this app is open."
                let message = canceled ? pauseMessage : (error as? LocalizedError)?.errorDescription ?? "Local processing could not finish. Retained files and existing voices were kept."
                do { try update(canceled ? "Paused" : "Needs attention", message) }
                catch { notice = "Could not save the latest status. Existing files were kept; check iPhone storage." }
            }
        }
    }
}
