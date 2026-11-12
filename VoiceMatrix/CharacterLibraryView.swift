import SwiftUI
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
        guard let root = Bundle.main.url(forResource: "F5TTS", withExtension: nil) else { return false }
        return FileManager.default.fileExists(atPath: root.appendingPathComponent("voicematrix-engine.json").path)
    }
    var conversionAvailable: Bool {
        guard let root = Bundle.main.url(forResource: "OpenVoice", withExtension: nil) else { return false }
        return FileManager.default.fileExists(atPath: root.appendingPathComponent("model-manifest.json").path)
    }
    init() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
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
    func releaseForLocalGeneration() async throws {
        guard !busy, !syncing else { throw CharacterImportError.invalid("Finish the current library operation first.") }
        await engine.unload()
    }
    func importLocalGeneratedCollection(_ url: URL) async throws {
        guard !busy, !syncing else { throw CharacterImportError.invalid("Finish the current library operation first.") }
        busy = true
        defer { busy = false }
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
        guard let model = Bundle.main.url(forResource: "F5TTS", withExtension: nil),
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

enum CharacterStudioMode: String, CaseIterable { case speech, conversion }

struct CharacterLibraryView: View {
    @State private var mode: CharacterStudioMode
    @StateObject private var recorder = Recorder()
    private enum ImportKind { case folder, audio }
    @State private var importKind: ImportKind = .folder
    @State private var showingImporter = false
    @State private var choosingVoice = false
    @State private var showingSyncLog = false
    @FocusState private var editingWords: Bool
    init(mode: CharacterStudioMode = .speech) { _mode = State(initialValue: mode) }
    @EnvironmentObject private var library: CharacterLibrary
    @Environment(\.scenePhase) private var scenePhase
    @EnvironmentObject private var audio: AudioStore
    @EnvironmentObject private var studio: SpeechStudio
    @State private var controls = SpeechControls()
    @State private var words = "Hello! Welcome to the character voice studio."
    var body: some View {
        List {
            Section {
                Button { choosingVoice = true } label: {
                    HStack(spacing: 14) {
                        Image(systemName: "person.wave.2.fill").font(.title2)
                            .foregroundStyle(StudioPalette.mint)
                        VStack(alignment: .leading, spacing: 5) {
                            Text("YOUR VOICE").font(.caption.weight(.bold)).tracking(1.5).foregroundStyle(.secondary)
                            Text(library.profiles.first(where: { $0.id == library.selectedID })?.name ?? "Choose a character")
                                .font(.title3.bold()).foregroundStyle(.primary)
                            Text(library.availableProfiles.isEmpty ? "Browse the laptop catalog to get started" : "Browse \(library.availableProfiles.count) voices · \(library.profiles.count) downloaded")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.down").font(.caption.bold())
                    }.padding(.vertical, 8)
                }.disabled(library.busy || recorder.recording).accessibilityIdentifier("choose-character")
                if library.selectedID.isEmpty {
                    Text("Choose a voice first, then type or record your words.")
                        .font(.subheadline).foregroundStyle(.secondary)
                        .accessibilityIdentifier("character-selection-guidance")
                }
            }
            Section {
                DisclosureGroup("Manage your collection") {
                    Button { library.syncVoices() } label: { Label("Refresh laptop catalog", systemImage: "arrow.triangle.2.circlepath") }
                        .disabled(library.busy || library.syncing || !LaptopConnection.paired)
                    if library.syncing { ProgressView(library.downloadingID == nil ? "Refreshing catalog…" : "Downloading voice…"); Button("Stop sync", role: .cancel) { library.cancelSync() }.disabled(!library.syncCanStop) }
                    Button { showingSyncLog = true } label: { Label("Live sync log", systemImage: "list.bullet.rectangle") }
                        .accessibilityIdentifier("live-sync-log")
                    if let latest = library.syncEvents.last { Text(latest.progress.message).font(.caption).foregroundStyle(.secondary) }
                    Button { importKind = .folder; showingImporter = true } label: { Label("Choose Voices Folder", systemImage: "folder.badge.plus") }
                        .disabled(library.busy || library.downloadingID != nil).accessibilityIdentifier("import-character-folder")
                    Text(library.catalogStatus).font(.caption).foregroundStyle(.secondary)
                    if let bytes = library.storedVoiceBytes {
                        Text("Saved voice files: " + ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Text("Refresh checks names and availability only. Download individual voices in the picker while online; downloaded and imported voices stay on this iPhone. The app refreshes when opened, not continuously in the background.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section {
                Picker("What would you like to do?", selection: $mode) {
                    Text("Make Speech").tag(CharacterStudioMode.speech)
                    Text("Change My Voice").tag(CharacterStudioMode.conversion)
                }.pickerStyle(.segmented).disabled(library.busy || recorder.recording)
            }
            if mode == .speech {
            Section("Make character speech") {
                Text(library.profiles.first(where: { $0.id == library.selectedID })?.name ?? "Choose an imported character above")
                TextEditor(text: $words).focused($editingWords).frame(minHeight: 140).accessibilityLabel("Words for your character")
                Text("\(words.count) characters · split into complete-word parts").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Text("No fixed character cap. Jobs are limited to about 30 minutes before speed changes; longer text must be split. Keep the app open. Long jobs use battery and storage.")
                    .font(.caption).foregroundStyle(.secondary)
                DisclosureGroup("Speech controls") {
                    Text(String(format: "Speed · %.2fx", controls.speed))
                    Slider(value: $controls.speed, in: 0.5...2, step: 0.05).accessibilityLabel("Speech speed")
                    Text(String(format: "Pitch · %+.0f semitones", controls.pitch))
                    Slider(value: $controls.pitch, in: -12...12, step: 1).accessibilityLabel("Speech pitch")
                    Text(String(format: "Volume · %.0f%%", controls.volume * 100))
                    Slider(value: $controls.volume, in: 0.25...1, step: 0.05).accessibilityLabel("Speech volume")
                    Text(String(format: "Pause between generated parts · %.2f seconds", controls.pause))
                    Slider(value: $controls.pause, in: 0...1, step: 0.05).accessibilityLabel("Speech part pause")
                    Button("Reset speech controls") { controls = SpeechControls() }.accessibilityIdentifier("reset-speech-controls")
                    Text("Applied when you create speech, including saved/shared audio. Pitch shifts may change resemblance. Reference recordings are unchanged.")
                        .font(.caption).foregroundStyle(.secondary)
                }.disabled(library.busy)

                Button { editingWords = false; audio.stop(); library.speak(words, audio: audio, studio: studio, controls: controls) } label: { Label("Create speech", systemImage: "waveform").font(.headline).frame(maxWidth: .infinity, minHeight: 48) }
                    .buttonStyle(.borderedProminent).accessibilityIdentifier("create-character-speech")
                    .disabled(library.busy || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse || !library.engineAvailable || words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if library.busy { ProgressView(library.message); Button("Stop after current step", role: .cancel) { library.cancel() } }
                Text(library.message).font(.caption).foregroundStyle(.secondary).accessibilityAddTraits(.updatesFrequently)
                if !library.engineAvailable { Text("The shared F5 engine is absent from this build. Your imported voice samples remain saved; speech testing becomes available in a build containing that engine.").foregroundStyle(.secondary) }
                Text("Creates new words using your selected voice.").font(.caption).foregroundStyle(.secondary)
                if let output = library.output, library.outputKind == "speech", library.outputMatchesSelection {
                    Text("Created with " + library.outputSettings).font(.caption).foregroundStyle(.secondary)
                    AudioActions(url: output)
                }
                else { Text("Create speech with this character to listen or save.").foregroundStyle(.secondary) }
            }
            } else {
                Section("1 · Record your words") {
                    Button {
                        if recorder.recording { recorder.stop() } else { Task { await recorder.start(audio: audio) } }
                    } label: { Label(recorder.recording ? "STOP RECORDING" : "RECORD MY VOICE", systemImage: recorder.recording ? "stop.fill" : "mic.fill").frame(minHeight: 52) }
                        .buttonStyle(.borderedProminent).disabled(library.busy || recorder.requestingPermission || (audio.processingInUse && !recorder.recording))
                    Button("Import Audio") { importKind = .audio; showingImporter = true }.disabled(library.busy || recorder.recording || recorder.requestingPermission)
                    Text(recorder.status)
                    Text("Use up to 10 seconds of clear speech. Your words and timing are processed locally.").font(.caption).foregroundStyle(.secondary)
                }
                Section("2 · Choose a character above, then Convert") {
                    Text(library.profiles.first(where: { $0.id == library.selectedID })?.name ?? "Choose a character above")
                    Button {
                        if let source = recorder.output { library.convertRecording(source, audio: audio, studio: studio) }
                    } label: { Label("CONVERT", systemImage: "waveform").frame(minHeight: 52) }.buttonStyle(.borderedProminent)
                        .disabled(library.busy || recorder.recording || recorder.requestingPermission || recorder.output == nil || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse || !library.conversionAvailable)
                if library.busy { ProgressView(library.message); Button("Stop after current step", role: .cancel) { library.cancel() } }
                    Text(library.message).font(.caption).foregroundStyle(.secondary).accessibilityAddTraits(.updatesFrequently)
                    if !library.conversionAvailable { Text("This build needs the shared voice-changing engine before conversion can run.").foregroundStyle(.secondary) }
                    if let source = recorder.output, !recorder.recording { Button("Listen to my original recording") { audio.play(source) }.disabled(library.busy) }
                    Text("Changes a recording on your iPhone. Not for live calls.").font(.caption).foregroundStyle(.secondary)
                    if let output = library.output, library.outputKind == "conversion", library.outputMatchesSelection { AudioActions(url: output) }
                }
            }
            Section { NavigationLink("Send a suggestion") { SuggestionsView() } }
            Section("Playback & comparison") {
                Text("Compare the original voice with your new audio.").font(.subheadline).foregroundStyle(.secondary)
                if let selected = library.profiles.first(where: { $0.id == library.selectedID }) {
                    Text("Selected: " + selected.name)
                } else {
                    Text("Choose a character at the top to hear its reference.")
                }
                Button { library.listenToReference(audio: audio) } label: { Label("1 · Listen to reference", systemImage: "person.wave.2") }
                    .disabled(library.busy || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse)
                TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Output: " + audio.outputRoute + " · Volume: " + String(audio.outputVolumePercent) + "%")
                            .font(.caption)
                        if audio.playing != nil {
                            Text(String(format: "Playing · %.1f / %.1f seconds", audio.elapsedSeconds, audio.durationSeconds))
                                .monospacedDigit().accessibilityIdentifier("character-playback-progress")
                        }
                    }
                }
                if audio.playing != nil {
                    Button("Stop playback") { audio.stop() }.accessibilityIdentifier("stop-character-playback")
                }
                if let error = audio.error {
                    Text(error).foregroundStyle(.orange).accessibilityIdentifier("character-playback-error")
                }
                if let output = library.output, library.canReview {
                    Button { audio.play(output) } label: { Label("2 · Listen to result", systemImage: "waveform") }
                    Button("Matches") { library.review(.matches) }.accessibilityIdentifier("character-match-yes")
                    Button("Doesn’t Match") { library.review(.different) }.accessibilityIdentifier("character-match-no")
                    Button("Unsure") { library.review(.unsure) }.accessibilityIdentifier("character-match-unsure")
                } else { Text("Create speech with the selected reference before reviewing it.").foregroundStyle(.secondary) }
                if let voice = library.profiles.first(where: { $0.id == library.selectedID }) { Text(library.matchDescription(voice)).font(.caption) }
            }
        }
        .navigationTitle(mode == .speech ? "Make Speech" : "Change My Voice")
        .scrollContentBackground(.hidden)
        .background(StudioPalette.background)
        .scrollDismissesKeyboard(.interactively)
        .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { editingWords = false } } }
        .sheet(isPresented: $showingSyncLog) { NavigationStack { VoiceSyncLogView() } }
        .sheet(isPresented: $choosingVoice) { NavigationStack { CharacterPickerView() } }
        // One presenter avoids the audio importer masking the folder importer.
        .fileImporter(isPresented: $showingImporter,
                      allowedContentTypes: importKind == .folder ? [.folder] : [.wav, .mpeg4Audio, .audio]) { result in
            switch (importKind, result) {
            case (.folder, .success(let url)): library.importFolder(url)
            case (.folder, .failure(let error)): library.message = "The folder could not be opened. " + error.localizedDescription
            case (.audio, .success(let url)): recorder.importAudio(url)
            case (.audio, .failure): recorder.status = "That recording could not be opened. Try a WAV or M4A file."
            }
        }
        .onDisappear { recorder.discard(); audio.stop() }
        .task {
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-ui-test-import"),
               library.profiles.isEmpty,
               let fixture = Bundle.main.url(forResource: "F5TTS", withExtension: nil)?.appendingPathComponent("UITestVoices"),
               FileManager.default.fileExists(atPath: fixture.path) {
                do {
                    let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("UIImport-" + UUID().uuidString)
                    try FileManager.default.copyItem(at: fixture, to: temporary)
                    library.importFolder(temporary)
                    while library.busy { try await Task.sleep(for: .milliseconds(100)) }
                    // Make the original source unavailable before restart: only the
                    // private imported copy can satisfy the persistence/playback test.
                    try FileManager.default.removeItem(at: temporary)
                } catch { library.message = "UI fixture import failed: " + error.localizedDescription }
            } else { await library.loadAndRefresh() }
            #else
            await library.loadAndRefresh()
            #endif
        }
        .onChange(of: scenePhase) { _, value in if value == .active { Task { await library.loadAndRefresh() } } }
    }
}

struct CharacterPickerView: View {
    @EnvironmentObject private var library: CharacterLibrary
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""
    @State private var category = "All"
    private var categories: [String] { ["All"] + Set(library.availableProfiles.flatMap(\.categories)).sorted() }
    private var filtered: [CharacterReference] {
        library.availableProfiles.filter {
            (category == "All" || $0.categories.contains(category)) &&
            (search.isEmpty || ([$0.name] + $0.categories).joined(separator: " ").localizedCaseInsensitiveContains(search))
        }
    }
    var body: some View {
        List {
            Section {
                Picker("Category", selection: $category) {
                    ForEach(categories, id: \.self) { Text($0).tag($0) }
                }
                Text("\(filtered.count) voices · \(library.profiles.count) downloaded").font(.caption).foregroundStyle(.secondary)
                Text(library.catalogStatus).font(.caption).foregroundStyle(.secondary)
                Button("Refresh laptop catalog") { library.syncVoices() }
                    .disabled(library.busy || library.syncing || !LaptopConnection.paired)
                if library.syncing {
                    ProgressView(library.downloadingID == nil ? "Refreshing catalog…" : "Downloading voice…")
                    Button("Stop sync", role: .cancel) { library.cancelSync() }.disabled(!library.syncCanStop)
                }
                Text(library.message).font(.caption).foregroundStyle(.secondary)
                Text("Online required for new downloads. Downloaded voices work without the laptop.").font(.caption).foregroundStyle(.secondary)
            }
            if filtered.isEmpty {
                ContentUnavailableView(library.availableProfiles.isEmpty ? "Browse your voices" : "No matching voices",
                    systemImage: "person.2.wave.2",
                    description: Text(library.availableProfiles.isEmpty ? "Connect through Tailscale and refresh the laptop catalog, or import your Voices folder." : "Try a different name or category."))
            }
            ForEach(filtered) { voice in
                VStack(alignment: .leading, spacing: 8) {
                    Button {
                        library.selectedID = voice.id
                        dismiss()
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: library.selectedID == voice.id ? "checkmark.circle.fill" : "person.crop.circle")
                                .font(.title2).foregroundStyle(StudioPalette.mint)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(voice.name).font(.headline).foregroundStyle(.primary)
                                Text(voice.categories.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                        }.padding(.vertical, 8)
                    }.buttonStyle(.plain).disabled(library.busy || !library.isDownloaded(voice.id))
                        .accessibilityIdentifier("select-character-" + voice.id)
                        .accessibilityValue(library.selectedID == voice.id ? "Selected" : "Not selected")
                    if library.isDownloaded(voice.id) {
                        Label("Downloaded · ready offline", systemImage: "checkmark.circle.fill").font(.caption).foregroundStyle(StudioPalette.mint)
                        if library.hasChangedRemoteReference(voice) {
                            Text("The laptop has a changed reference. Your saved version is kept until a reviewed replacement is supported.").font(.caption).foregroundStyle(.secondary)
                        }
                    } else {
                        Button { library.downloadVoice(voice) } label: { Label("Download for offline · " + library.downloadSize(voice.id), systemImage: "arrow.down.circle") }
                            .disabled(library.busy || library.syncing || !LaptopConnection.paired)
                            .accessibilityIdentifier("download-character-" + voice.id)
                        Text("Online required · available on laptop").font(.caption).foregroundStyle(.secondary)
                    }
                    DisclosureGroup("Voice details") {
                        Text("Source: " + voice.source)
                        Text("Permission record: " + voice.permission)
                        Text(library.matchDescription(voice)).font(.caption)
                    }.font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .task { await library.loadAndRefresh() }
        .navigationTitle("Choose a voice")
        .searchable(text: $search, prompt: "Search names or categories")
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        .scrollContentBackground(.hidden).background(StudioPalette.background)
    }
}


private struct VoiceSyncLogView: View {
    @EnvironmentObject private var library: CharacterLibrary
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        List {
            Section {
                if library.syncing, let started = library.syncStarted {
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        Text("Sync running · \(Int(context.date.timeIntervalSince(started))) seconds elapsed")
                        if let last = library.syncEvents.last {
                            Text("Last activity \(max(0, Int(context.date.timeIntervalSince(last.date)))) seconds ago. Waiting is not proof of progress.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Button("Stop sync", role: .cancel) { library.cancelSync() }.disabled(!library.syncCanStop)
                } else {
                    Button("Refresh laptop catalog") { library.syncVoices() }
                        .disabled(library.busy || !LaptopConnection.paired)
                }
                Text("Laptop entries are based on received responses. iPhone entries show download, validation and saving. No voice names, recordings or transcripts are logged.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Latest activity first") {
                if library.syncEvents.isEmpty { Text("No sync activity in this app session yet.") }
                ForEach(library.syncEvents.reversed()) { event in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(event.progress.message)
                        Text("\(event.date.formatted(date: .omitted, time: .standard)) · \(event.progress.source)")
                            .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Live sync log")
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
    }
}
