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
        var sourceFile: String?
        var sourceSHA256: String?
        var referenceFile: String?
        var previewFile: String?
        var voiceID: String?
        var completed = false
        var events: [Event] = []
    }
    @Published private(set) var current: Job?
    @Published private(set) var history: [Job] = []
    @Published private(set) var busy = false
    @Published private(set) var notice = "Import an authorized local video or recording. This path does not use a laptop or server."
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
            guard safe(job.sourceFile), safe(job.referenceFile), safe(job.previewFile) else { return nil }
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
    func selectHistory(_ job: Job) { guard !busy else { return }; current = job }
    func setActive(_ value: Bool) { active = value; if !value, busy { cancel() } }
    func cancel() { guard busy else { return }; operation?.cancel(); try? update("Stopping", "Stopping at a safe boundary. Source and completed outputs are retained.") }
    func start(_ source: URL, authorized: Bool, library: CharacterLibrary, audio: AudioStore, speech: SpeechStudio) {
        guard authorized, !busy, active else { return }
        do {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            let free = try root.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]).volumeAvailableCapacityForImportantUsage ?? 0
            var retained: Int64 = 0
            let entries = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.fileSizeKey, .isRegularFileKey])
            while let url = entries?.nextObject() as? URL {
                let value = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
                if value.isRegularFile == true { retained += Int64(value.fileSize ?? 0) }
            }
            guard free >= 800_000_000, retained < 2_000_000_000 else { throw LocalError.storage }
            let now = Date()
            current = Job(id: UUID(), created: now, updated: now, stage: "Received", message: "Local media selected; preparing a retained copy.")
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: false)
            try update("Received", "App received the selected local media. Nothing is uploaded.")
            run(source: source, library: library, audio: audio, speech: speech)
        } catch { notice = "Could not start a local job. Check free storage; existing voices were kept." }
    }
    func resume(library: CharacterLibrary, audio: AudioStore, speech: SpeechStudio) {
        guard !busy, active, let job = current, !job.completed, job.sourceFile != nil else { return }
        run(source: nil, library: library, audio: audio, speech: speech)
    }
    private enum LocalError: LocalizedError {
        case storage, source, candidate, preview, engine, thermal
        var errorDescription: String? {
            switch self {
            case .storage: return "Free at least 800 MB. Retained local jobs have a 2 GB admission limit; no old files were deleted."
            case .source: return "The retained source is missing, changed or unsupported. Existing voices were kept."
            case .candidate: return "No acceptable reference was found. This mode does not separate overlapping speakers or identify characters."
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
            defer { busy = false; audio.releaseProcessing(lease); reloadHistory() }
            do {
                try check()
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
                        while let bytes = try input.read(upToCount: 1_048_576), !bytes.isEmpty {
                            try Task.checkCancellation(); count += bytes.count
                            guard count <= size else { throw LocalError.source }
                            try output.write(contentsOf: bytes); hash.update(data: bytes)
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
                try update("Checking local transcription", "Checking English on-device recognition. Server recognition is disabled.")
                try await transcriber.authorize()
                let duration = try await AVURLAsset(url: retained).load(.duration).seconds
                let windows = LocalStudioEvidence.windows(duration: duration)
                guard !windows.isEmpty else { throw LocalError.source }
                try await library.releaseForLocalGeneration(); await speech.releaseModelsForCharacter()
                guard let bundle = Bundle.main.url(forResource: "F5TTS", withExtension: nil) else { throw LocalError.engine }
                var previews = 0
                for (index, window) in windows.enumerated() {
                    try check()
                    try update("Selecting reference", "Checking window \(index + 1) of \(windows.count). This is one-reference mode, not speaker separation.")
                    let clip: LocalVideoAudio.Reference
                    do { clip = try await LocalVideoAudio.extract(source: retained, start: window.start, seconds: window.seconds) }
                    catch LocalVideoAudio.Failure.unusableAudio { continue }
                    let attempt = UUID().uuidString.lowercased()
                    let reference = jobFolder.appendingPathComponent("reference-" + attempt + ".wav")
                    try clip.wave.write(to: reference, options: .atomic)
                    current?.referenceFile = reference.lastPathComponent
                    try update("Transcribing reference", "Recognizing this candidate locally. Identity and overlap are not verified.")
                    let transcript: String
                    do { transcript = try await transcriber.transcribe(reference) { [weak self] in try? self?.update("Transcribing reference", "On-device recognition is producing results.", log: false) } }
                    catch OnDeviceTranscription.Failure.noSpeech { continue }
                    try Data(transcript.utf8).write(to: jobFolder.appendingPathComponent("transcript-" + attempt + ".txt"), options: .atomic)
                    try check(); previews += 1
                    try update("Generating preview", "Loading the bundled F5 engine and generating preview \(previews) of at most 3. No laptop or server is used.")
                    let preview = jobFolder.appendingPathComponent("preview-" + attempt + ".wav")
                    try await engine.load(localBundle: bundle)
                    try await engine.speak(text: previewText, referenceAudio: reference, referenceText: transcript, destination: preview) { [weak self] part, total in
                        Task { @MainActor in guard let self, self.runToken == run, self.busy else { return }; try? self.update("Generating preview", "Generating speech part \(part) of \(total).", log: false) }
                    }
                    await engine.finishRequest(keepWarm: false)
                    current?.previewFile = preview.lastPathComponent
                    try update("Verifying preview", "Checking the generated words locally. This does not verify likeness.")
                    let recognized: String
                    do { recognized = try await transcriber.transcribe(preview) }
                    catch OnDeviceTranscription.Failure.noSpeech { if previews >= 3 { throw LocalError.preview }; continue }
                    guard LocalStudioEvidence.wordErrorRate(expected: previewText, actual: recognized) <= 0.1 else {
                        try update("Preview rejected", "Spoken words did not pass. This preview is retained but will not be imported.")
                        if previews >= 3 { throw LocalError.preview }; continue
                    }
                    try check()
                    let id = "local-" + current!.id.uuidString.lowercased()
                    let collection = jobFolder.appendingPathComponent("collection-" + attempt, isDirectory: true)
                    let voiceFolder = collection.appendingPathComponent(id, isDirectory: true)
                    try FileManager.default.createDirectory(at: voiceFolder, withIntermediateDirectories: true)
                    let metadata: [String: Any] = ["id": id, "name": "Unidentified reference " + String(current!.id.uuidString.prefix(6)), "source": "User-authorized local media SHA256 " + expectedHash, "permission": "User affirmed source-use authorization in the local studio", "referenceText": transcript, "schemaVersion": 1, "kind": "f5-reference", "engine": "F5TTS_v1_Base", "referenceFile": "reference.wav", "referenceSHA256": Self.hash(clip.wave), "trainedModel": false, "categories": ["Local", "Unidentified", "Preview-only"], "referenceBytes": clip.wave.count, "seconds": clip.seconds]
                    try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys]).write(to: voiceFolder.appendingPathComponent("manifest.json"), options: .atomic)
                    try clip.wave.write(to: voiceFolder.appendingPathComponent("reference.wav"), options: .atomic)
                    try JSONSerialization.data(withJSONObject: ["schemaVersion": 1, "voices": [["id": id, "folder": id]]]).write(to: collection.appendingPathComponent("collection.json"), options: .atomic)
                    try update("Importing", "Atomically validating and registering the preview-only reference on this iPhone.")
                    try await library.importLocalGeneratedCollection(collection)
                    current?.voiceID = id; current?.completed = true
                    try update("Reference ready", "One local reference is saved and its preview passed the word check. Listen to judge resemblance; character identity, separation and RVC training are not verified.")
                    return
                }
                throw LocalError.candidate
            } catch {
                await engine.finishRequest(keepWarm: false)
                let canceled = error is CancellationError || Task.isCancelled
                let message = canceled ? "Paused. Retained source and completed outputs are safe. Resume while this app is open." : (error as? LocalizedError)?.errorDescription ?? "Local processing could not finish. Retained files and existing voices were kept."
                do { try update(canceled ? "Paused" : "Needs attention", message) }
                catch { notice = "Could not save the latest status. Existing files were kept; check iPhone storage." }
            }
        }
    }
}
