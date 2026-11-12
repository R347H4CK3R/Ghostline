import Foundation
import Combine
import UniformTypeIdentifiers
import CryptoKit

@MainActor final class CharacterLibrary: ObservableObject {
    @Published var profiles: [CharacterReference] = []
    @Published private(set) var remoteCatalog: RemoteVoiceCatalog?
    @Published private(set) var catalogCheckedAt: Date?
    @Published private(set) var catalogReachable = false
    @Published private(set) var downloadingID: String?
    @Published private(set) var storedVoiceBytes: Int64?
    private var lastCatalogAttempt: Date?
    private var loadedCatalogCache = false
    var availableProfiles: [CharacterReference] {
        let savedIDs = Set(profiles.map(\.id))
        return (profiles + (remoteCatalog?.voices ?? []).filter { !savedIDs.contains($0.id) })
            .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }
    func isDownloaded(_ id: String) -> Bool { profiles.contains { $0.id == id } }
    func downloadSize(_ id: String) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(remoteCatalog?.downloadBytes(id: id) ?? 0), countStyle: .file)
    }
    func hasChangedRemoteReference(_ voice: CharacterReference) -> Bool {
        guard let remote = remoteCatalog?.voices.first(where: { $0.id == voice.id }) else { return false }
        return remote.referenceSHA256 != voice.referenceSHA256 || remote.referenceText != voice.referenceText
    }
    var catalogStatus: String {
        if syncing { return downloadingID == nil ? "Refreshing laptop catalog…" : "Downloading selected voice…" }
        if let catalogCheckedAt {
            return (catalogReachable ? "Last connected " : "Cached catalog · last connected ") + catalogCheckedAt.formatted(date: .abbreviated, time: .shortened)
        }
        return "Connect to your laptop through Tailscale to browse and download voices."
    }
    @Published var busy = false
    @Published private(set) var syncing = false
    @Published private(set) var syncCanStop = false
    @Published private(set) var syncEvents: [VoiceSyncLogEntry] = []
    @Published private(set) var syncStarted: Date?
    private var syncRunID = UUID()
    private func recordSync(_ progress: VoiceSyncProgress) {
        if progress.isTerminal || progress == .stopping { syncCanStop = false }
        syncEvents.append(VoiceSyncLogEntry(progress: progress))
        if syncEvents.count > 200 { syncEvents.removeFirst(syncEvents.count - 200) }
    }
    @Published var selectedID = ""
    @Published var output: URL?
    @Published private(set) var outputKind = "speech"
    @Published private(set) var outputSettings = ""
    @Published private(set) var outputCharacterID = ""
    @Published private(set) var outputReferenceHash = ""
    @Published private(set) var reviewSummaries: [String: CharacterListeningReview] = [:]
    @Published var message = "Browse your laptop catalog, then download the voices you want to use offline. Existing imported voices stay saved."
    private let f5Bundle: URL?
    private let remoteCache: RemoteVoiceCatalogCache
    private let store: CharacterFolderStore
    private let reviewStore: CharacterReviewStore
    private let engine = F5ReferenceEngine()
    private let voiceChanger = CharacterVoiceConversion()
    private var operationID = UUID()
    private var job: Task<Void, Never>?
    private var syncJob: Task<Void, Never>?
    private var catalogRefresh = UUID()
    private var reviewRefresh = UUID()
    private var applicationActive = true
    private var retainCurrentSpeech = true
    func releaseWarmSpeech() {
        retainCurrentSpeech = false
        Task { await engine.requestRelease() }
    }
    func setApplicationActive(_ active: Bool) {
        applicationActive = active
        if !active {
            releaseWarmSpeech()
            // Switching to Tailscale to reconnect must allow an immediate retry.
            if syncing || !catalogReachable { lastCatalogAttempt = nil }
            catalogReachable = false
            cancelSync()
        }
        else {
            Task {
                // The canceled job must finish releasing its session before a
                // foreground refresh can acquire the single-sync slot.
                if let interrupted = syncJob, interrupted.isCancelled { await interrupted.value }
                await loadAndRefresh()
            }
        }
    }
    var engineAvailable: Bool {
        guard let root = f5Bundle else { return false }
        return FileManager.default.fileExists(atPath: root.appendingPathComponent("voicematrix-engine.json").path)
    }
    var conversionAvailable: Bool {
        guard let root = Bundle.main.url(forResource: "OpenVoice", withExtension: nil) else { return false }
        return FileManager.default.fileExists(atPath: root.appendingPathComponent("model-manifest.json").path)
    }
    init(supportRoot: URL? = nil, f5Bundle: URL? = Bundle.main.url(forResource: "F5TTS", withExtension: nil)) {
        self.f5Bundle = f5Bundle
        let support = supportRoot ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        remoteCache = RemoteVoiceCatalogCache(file: support.appendingPathComponent("RemoteVoiceCatalog/catalog.json"))
        store = CharacterFolderStore(root: support.appendingPathComponent("CharacterReferences", isDirectory: true))
        reviewStore = CharacterReviewStore(root: support.appendingPathComponent("CharacterReviews", isDirectory: true))
    }
    func loadAndRefresh() async {
        guard !busy else { return }
        let ticket = UUID(); catalogRefresh = ticket
        do {
            let saved = try await store.profiles()
            guard catalogRefresh == ticket, !busy else { return }
            profiles = saved
            storedVoiceBytes = try? await store.storedBytes()
            if !loadedCatalogCache {
                loadedCatalogCache = true
                if let cached = try? await remoteCache.load(), remoteCatalog == nil {
                    remoteCatalog = cached.catalog; catalogCheckedAt = cached.checkedAt
                }
            }
            await refreshReviewSummaries()
        }
        catch { message = error.localizedDescription; return }
        if LaptopConnection.paired { syncVoices(force: false); return }
        // Imported references already live in private storage. Do not silently import
        // new audio from an old bookmark when automatic catalog refresh runs offline.
    }
    func cancelSync() { guard syncCanStop else { return }; recordSync(.stopping); syncJob?.cancel() }
    /// Retains the old action name for callers, but automatic sync is now metadata only.
    func syncVoices(force: Bool = true) {
        guard !busy, !syncing, applicationActive, LaptopConnection.paired else { return }
        if !force, let lastCatalogAttempt, Date().timeIntervalSince(lastCatalogAttempt) < 60 { return }
        lastCatalogAttempt = Date()
        syncing = true; syncCanStop = true
        syncEvents = []; syncStarted = Date()
        let run = UUID(); syncRunID = run
        recordSync(.requesting)
        syncJob = Task {
            defer { syncing = false; syncCanStop = false }
            do {
                let catalog = try await LaptopConnection.voiceCatalog(syncID: run.uuidString.lowercased(), progress: { [weak self] event in
                    await self?.receiveSync(event, run: run)
                })
                try Task.checkCancellation()
                let unchanged = remoteCatalog?.revision == catalog.revision
                let checkedAt = Date()
                try await remoteCache.save(catalog, checkedAt: checkedAt)
                try Task.checkCancellation()
                remoteCatalog = catalog; catalogCheckedAt = checkedAt; catalogReachable = true
                if unchanged { recordSync(.unchanged) }
                else { recordSync(.catalogRefreshed(catalog.voices.count)) }
                if !busy { message = "\(catalog.voices.count) voices available on your laptop. Download only the ones you want offline." }
            } catch {
                catalogReachable = false
                recordSync(Task.isCancelled ? .stopped : .failed)
                if !busy { message = Task.isCancelled ? "Catalog refresh stopped. Downloaded voices were kept." : "Laptop unavailable. Downloaded voices still work offline; connect through Tailscale to refresh or download. " + error.localizedDescription }
            }
        }
    }
    func downloadVoice(_ voice: CharacterReference) {
        guard !busy, !syncing, applicationActive, LaptopConnection.paired, !isDownloaded(voice.id),
              remoteCatalog?.voices.contains(where: { $0 == voice }) == true else { return }
        syncing = true; syncCanStop = true; downloadingID = voice.id
        syncEvents = []; syncStarted = Date()
        let run = UUID(); syncRunID = run
        recordSync(.requesting)
        syncJob = Task {
            let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("VoiceSync-" + UUID().uuidString)
            defer { syncing = false; syncCanStop = false; downloadingID = nil; try? FileManager.default.removeItem(at: temporary) }
            do {
                let catalog = try await LaptopConnection.downloadVoice(voice, to: temporary, syncID: run.uuidString.lowercased(), progress: { [weak self] event in
                    await self?.receiveSync(event, run: run)
                })
                try Task.checkCancellation()
                guard !busy else { recordSync(.deferred); message = "Download finished while audio was busy. Download again when it finishes."; return }
                busy = true
                defer { busy = false }
                recordSync(.importing)
                profiles = try await store.importCollection(at: temporary)
                // Once the atomic import committed, a late Stop must not misreport failure.
                recordSync(.completed(1))
                storedVoiceBytes = try? await store.storedBytes()
                remoteCatalog = catalog; catalogCheckedAt = Date(); catalogReachable = true
                if let checkedAt = catalogCheckedAt { try? await remoteCache.save(catalog, checkedAt: checkedAt) }
                await refreshReviewSummaries()
                message = "\(voice.name) downloaded for offline use. Choose it to create speech."
            } catch {
                catalogReachable = false
                recordSync(Task.isCancelled ? .stopped : .failed)
                if !busy { message = Task.isCancelled ? "Download stopped. Existing voices were kept." : "Download unavailable. Connect to the laptop through Tailscale, refresh the catalog and retry. Existing voices were kept. " + error.localizedDescription }
            }
        }
    }
    private func receiveSync(_ event: VoiceSyncProgress, run: UUID) {
        guard syncing, syncCanStop, syncRunID == run, !Task.isCancelled else { return }
        recordSync(event)
    }
    private var localGenerationOwner: UUID?
    func beginLocalGeneration() async throws -> UUID {
        guard !busy, localGenerationOwner == nil else { throw CharacterImportError.invalid("Finish the current library operation first.") }
        let owner = UUID(); localGenerationOwner = owner; busy = true
        // Optional laptop catalog refresh must never gate standalone generation.
        syncJob?.cancel()
        if let pending = syncJob { await pending.value }
        await engine.unload()
        return owner
    }
    func endLocalGeneration(_ owner: UUID) {
        guard localGenerationOwner == owner else { return }
        localGenerationOwner = nil; busy = false
    }
    func importLocalGeneratedCollection(_ url: URL, owner: UUID) async throws {
        guard localGenerationOwner == owner, busy else { throw CharacterImportError.invalid("The local generation owner changed; existing voices were kept.") }
        profiles = try await store.importCollection(at: url)
        storedVoiceBytes = try? await store.storedBytes()
        if let data = try? Data(contentsOf: url.appendingPathComponent("collection.json")),
           let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let first = (value["voices"] as? [[String: String]])?.first, let id = first["id"] { selectedID = id }
        await refreshReviewSummaries()
        message = "Local preview-only reference saved. Listen before judging resemblance; identity is not verified."
    }
    func importFolder(_ url: URL) {
        guard !busy, downloadingID == nil else { return }
        catalogRefresh = UUID()
        busy = true; message = "Checking and copying your voices…"
        job = Task {
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() }; busy = false }
            do {
                profiles = try await store.importCollection(at: url)
                storedVoiceBytes = try? await store.storedBytes()
                await refreshReviewSummaries()
                // Save access only after the whole collection passes validation.
                if let bookmark = try? url.bookmarkData(options: .minimalBookmark, includingResourceValuesForKeys: nil, relativeTo: nil) {
                    UserDefaults.standard.set(bookmark, forKey: "characterFolderBookmark.v1")
                }
                message = "\(profiles.count) voice samples saved. " + (engineAvailable ? "Choose one to try speech." : "A build containing the shared F5 engine is needed to create speech.") + " Character resemblance has not been verified."
            } catch {
                message = error is CancellationError ? "Import stopped. Previously imported voices were kept." : "Import failed. Previously imported voices were kept. " + error.localizedDescription
            }
        }
    }
    private func refreshReviewSummaries() async {
        let ticket = UUID(); reviewRefresh = ticket
        let snapshot = profiles
        var next: [String: CharacterListeningReview] = [:]
        for voice in snapshot {
            do { next[voice.id] = try await reviewStore.latest(id: voice.id, referenceHash: voice.referenceSHA256) }
            catch { message = "Listening history could not be read. Your voices are still saved." }
        }
        guard reviewRefresh == ticket else { return }
        reviewSummaries = next.filter { id, summary in profiles.contains(where: { $0.id == id && $0.referenceSHA256 == summary.referenceSHA256 }) }
    }
    func matchDescription(_ voice: CharacterReference) -> String {
        switch reviewSummaries[voice.id]?.decision(forReferenceSHA256: voice.referenceSHA256) {
        case .matches: return "You marked this reference as a character match. Engine and audio checks remain separate."
        case .different: return "Doesn’t match. Waiting for a better reference; this decision is kept in your history."
        case .unsure: return "Unsure. Compare the recordings again before approving this character."
        case nil: return "Character match: awaiting your listening comparison"
        }
    }
    var outputMatchesSelection: Bool {
        guard output != nil, let voice = profiles.first(where: { $0.id == selectedID }) else { return false }
        return CharacterAudioIdentity(characterID: outputCharacterID, referenceSHA256: outputReferenceHash).matches(characterID: voice.id, referenceSHA256: voice.referenceSHA256)
    }
    var canReview: Bool { !busy && outputMatchesSelection }
    func listenToReference(audio: AudioStore) {
        guard !busy, let voice = profiles.first(where: { $0.id == selectedID }) else { return }
        Task {
            do { let url = try await store.referenceURL(id: voice.id); audio.play(url) }
            catch { message = error.localizedDescription }
        }
    }
    func review(_ decision: CharacterMatchDecision) {
        guard canReview, let output, let voice = profiles.first(where: { $0.id == selectedID }) else { return }
        busy = true
        job = Task {
            defer { busy = false }
            do {
                _ = try await store.referenceURL(id: voice.id)
                let hash = SHA256.hash(data: try Data(contentsOf: output)).map { String(format: "%02x", $0) }.joined()
                try await reviewStore.record(id: voice.id, referenceHash: voice.referenceSHA256, generatedHash: hash, decision: decision, categories: voice.categories)
                await refreshReviewSummaries()
                message = matchDescription(voice)
            } catch { message = "Your listening decision could not be saved. " + error.localizedDescription }
        }
    }
    func convertRecording(_ source: URL, audio: AudioStore, studio: SpeechStudio) {
        guard !busy, let voice = profiles.first(where: { $0.id == selectedID }) else { return }
        guard conversionAvailable else { message = "This build does not contain the voice-changing engine. Your references are still saved."; return }
        guard let lease = audio.claimProcessing() else { message = "Stop recording or the other speech task first."; return }
        let copy = FileManager.default.temporaryDirectory.appendingPathComponent("Imported-Character-" + UUID().uuidString + ".wav")
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent("Converted-" + voice.id + "-" + UUID().uuidString + ".wav")
        do { try FileManager.default.copyItem(at: source, to: copy) }
        catch { audio.releaseProcessing(lease); TemporaryAudio.discard(copy); message = "Your recording could not be prepared. Try recording again."; return }
        audio.stop(); busy = true; message = "Preparing your character…"
        let token = UUID(); operationID = token
        job = Task {
            defer { busy = false; audio.releaseProcessing(lease); TemporaryAudio.discard(copy) }
            do {
                await studio.releaseModelsForCharacter()
                await engine.unload()
                let reference = try await store.referenceURL(id: voice.id)
                _ = try await voiceChanger.run(reference: reference, source: copy, destination: destination) { stage in
                    Task { @MainActor in if self.busy && self.operationID == token { self.message = stage } }
                }
                try Task.checkCancellation()
                TemporaryAudio.discard(output); output = destination; outputKind = "conversion"
                outputCharacterID = voice.id; outputReferenceHash = voice.referenceSHA256
                message = "Your changed recording is ready to listen, save or share. Please compare the character resemblance."
            } catch {
                TemporaryAudio.discard(destination)
                message = error is CancellationError || Task.isCancelled ? "Stopped. Your saved voices were kept." : "Your voice could not be changed. " + error.localizedDescription
            }
        }
    }
    func cancel() { job?.cancel() }
    func speak(_ words: String, audio: AudioStore, studio: SpeechStudio, controls: SpeechControls = SpeechControls()) {
        let text = words.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, let voice = profiles.first(where: { $0.id == selectedID }) else { return }
        guard !text.isEmpty, controls.isValid else { message = "Type your words and choose valid speech controls."; return }
        guard let model = f5Bundle,
              FileManager.default.fileExists(atPath: model.appendingPathComponent("config.json").path) else {
            message = "This build does not contain the F5 speech engine. Your imported voice samples are safe; install a build containing the shared engine to test speech."; return
        }
        guard let lease = audio.claimProcessing() else { message = "Stop the other recording or speech task first."; return }
        retainCurrentSpeech = true
        busy = true; message = "Starting the local character speech engine…"
        let token = UUID(); operationID = token
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-" + voice.id + "-" + UUID().uuidString + ".wav")
        let raw = destination.deletingPathExtension().appendingPathExtension("raw.wav")
        job = Task {
            defer { busy = false; audio.releaseProcessing(lease); try? FileManager.default.removeItem(at: raw) }
            do {
                await studio.releaseModelsForCharacter()
                let reference = try await store.referenceURL(id: voice.id)
                try await engine.load(localBundle: model)
                message = "Creating speech as " + voice.name + "…"
                try await engine.speak(text: text, referenceAudio: reference, referenceText: voice.referenceText, destination: raw, pauseSeconds: controls.pause) { part, total in
                    Task { @MainActor in if self.busy && self.operationID == token { self.message = "Creating part \(part) of \(total)…" } }
                }
                try Task.checkCancellation()
                if controls.needsRendering { await engine.unload() }
                message = "Applying speed, pitch and volume…"
                try await SpeechRendering.render(source: raw, destination: destination, controls: controls)
                try Task.checkCancellation()
                TemporaryAudio.discard(output); output = destination; outputKind = "speech"
                outputSettings = controls.summary
                outputCharacterID = voice.id; outputReferenceHash = voice.referenceSHA256
                message = "Ready to listen, save or share. Please judge the character resemblance by listening; it has not been verified."
                await engine.finishRequest(keepWarm: retainCurrentSpeech && applicationActive && !controls.needsRendering)
            } catch {
                try? FileManager.default.removeItem(at: destination)
                message = error is CancellationError || Task.isCancelled ? "Stopped. Your saved voices were kept." : "Speech could not be created. " + error.localizedDescription
                await engine.finishRequest(keepWarm: false)
            }
        }
    }
}

