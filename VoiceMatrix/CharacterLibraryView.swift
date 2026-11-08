import SwiftUI
import UniformTypeIdentifiers
import CryptoKit

@MainActor final class CharacterLibrary: ObservableObject {
    @Published var profiles: [CharacterReference] = []
    @Published var busy = false
    @Published private(set) var syncing = false
    @Published var selectedID = ""
    @Published var output: URL?
    @Published private(set) var outputKind = "speech"
    @Published private(set) var outputCharacterID = ""
    @Published private(set) var outputReferenceHash = ""
    @Published private(set) var reviewSummaries: [String: CharacterListeningReview] = [:]
    @Published var message = "Choose your Voices collection folder once. Your voice samples are copied privately to this iPhone."
    private let store: CharacterFolderStore
    private let reviewStore: CharacterReviewStore
    private let engine = F5ReferenceEngine()
    private let voiceChanger = CharacterVoiceConversion()
    private var operationID = UUID()
    private var job: Task<Void, Never>?
    private var syncJob: Task<Void, Never>?
    private var catalogRefresh = UUID()
    private var reviewRefresh = UUID()
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
        store = CharacterFolderStore(root: support.appendingPathComponent("CharacterReferences", isDirectory: true))
        reviewStore = CharacterReviewStore(root: support.appendingPathComponent("CharacterReviews", isDirectory: true))
    }
    func loadAndRefresh() async {
        guard !busy else { return }
        let ticket = UUID(); catalogRefresh = ticket
        do {
            let saved = try await store.profiles()
            guard catalogRefresh == ticket, !busy else { return }
            profiles = saved; await refreshReviewSummaries()
        }
        catch { message = error.localizedDescription; return }
        if LaptopConnection.paired { syncVoices(); return }
        guard !busy, let data = UserDefaults.standard.data(forKey: "characterFolderBookmark.v1") else { return }
        do {
            var stale = false
            let url = try URL(resolvingBookmarkData: data, options: .withoutUI, relativeTo: nil, bookmarkDataIsStale: &stale)
            importFolder(url)
        } catch { message = "The master folder is unavailable. Your imported voices remain on this iPhone. Choose the folder again to refresh it." }
    }
    func cancelSync() { syncJob?.cancel() }
    func syncVoices() {
        guard !busy, !syncing, LaptopConnection.paired else { return }
        syncing = true
        syncJob = Task {
            let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("VoiceSync-" + UUID().uuidString)
            defer { syncing = false; try? FileManager.default.removeItem(at: temporary) }
            do {
                let previous = profiles.isEmpty ? nil : UserDefaults.standard.string(forKey: "remoteVoiceRevision.v1")
                guard let revision = try await LaptopConnection.syncVoices(to: temporary, previousRevision: previous) else { return }
                try Task.checkCancellation()
                guard !busy else { return } // Never interrupt active speech, recording conversion or listening review.
                busy = true
                defer { busy = false }
                profiles = try await store.importCollection(at: temporary)
                UserDefaults.standard.set(revision, forKey: "remoteVoiceRevision.v1")
                await refreshReviewSummaries()
                message = "\(profiles.count) character references saved for offline use. Character resemblance still needs listening review."
            } catch {
                if !busy { message = Task.isCancelled ? "Sync stopped. Your saved voices were kept." : "Laptop sync unavailable. Your saved voices remain usable offline. " + error.localizedDescription }
            }
        }
    }
    func importFolder(_ url: URL) {
        guard !busy else { return }
        catalogRefresh = UUID()
        busy = true; message = "Checking and copying your voices…"
        job = Task {
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() }; busy = false }
            do {
                profiles = try await store.importCollection(at: url)
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
    func speak(_ words: String, audio: AudioStore, studio: SpeechStudio) {
        let text = words.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, let voice = profiles.first(where: { $0.id == selectedID }) else { return }
        guard !text.isEmpty, text.count <= 500 else { message = "Type between 1 and 500 characters for this experimental engine."; return }
        guard let model = Bundle.main.url(forResource: "F5TTS", withExtension: nil),
              FileManager.default.fileExists(atPath: model.appendingPathComponent("config.json").path) else {
            message = "This build does not contain the F5 speech engine. Your imported voice samples are safe; install a build containing the shared engine to test speech."; return
        }
        guard let lease = audio.claimProcessing() else { message = "Stop the other recording or speech task first."; return }
        busy = true; message = "Starting the local character speech engine…"
        let token = UUID(); operationID = token
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-" + voice.id + "-" + UUID().uuidString + ".wav")
        job = Task {
            defer { busy = false; audio.releaseProcessing(lease) }
            do {
                await studio.releaseModelsForCharacter()
                let reference = try await store.referenceURL(id: voice.id)
                try await engine.load(localBundle: model)
                message = "Creating speech as " + voice.name + "…"
                try await engine.speak(text: text, referenceAudio: reference, referenceText: voice.referenceText, destination: destination) { part, total in
                    Task { @MainActor in if self.busy && self.operationID == token { self.message = "Creating part \(part) of \(total)…" } }
                }
                try Task.checkCancellation()
                TemporaryAudio.discard(output); output = destination; outputKind = "speech"
                outputCharacterID = voice.id; outputReferenceHash = voice.referenceSHA256
                message = "Ready to listen, save or share. Please judge the character resemblance by listening; it has not been verified."
            } catch {
                try? FileManager.default.removeItem(at: destination)
                message = error is CancellationError || Task.isCancelled ? "Stopped. Your saved voices were kept." : "Speech could not be created. " + error.localizedDescription
            }
            await engine.unload()
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
    init(mode: CharacterStudioMode = .speech) { _mode = State(initialValue: mode) }
    @EnvironmentObject private var library: CharacterLibrary
    @Environment(\.scenePhase) private var scenePhase
    @EnvironmentObject private var audio: AudioStore
    @EnvironmentObject private var studio: SpeechStudio
    @State private var search = ""
    @State private var category = "All"
    @State private var words = "Hello! Welcome to the character voice studio."
    private var categories: [String] { ["All"] + Set(library.profiles.flatMap(\.categories)).sorted() }
    private var filtered: [CharacterReference] {
        library.profiles.filter {
            (category == "All" || $0.categories.contains(category)) &&
            (search.isEmpty || ([$0.name] + $0.categories).joined(separator: " ").localizedCaseInsensitiveContains(search))
        }
    }
    var body: some View {
        List {
            Section {
                Button { library.syncVoices() } label: { Label("Sync voices from laptop", systemImage: "arrow.triangle.2.circlepath") }.disabled(library.busy || library.syncing || !LaptopConnection.paired)
                if library.syncing { ProgressView("Syncing laptop voices…"); Button("Stop sync", role: .cancel) { library.cancelSync() } }
                Button { importKind = .folder; showingImporter = true } label: { Label("Choose Voices Folder", systemImage: "folder.badge.plus") }
                    .disabled(library.busy).accessibilityIdentifier("import-character-folder")
                Text(library.message).font(.callout).accessibilityAddTraits(.updatesFrequently)
                if library.busy { ProgressView("Working…"); Button("Stop after current step", role: .cancel) { library.cancel() } }
                Text("This imports reusable reference profiles, rather than preview recordings or trained voice-conversion models. Their shared speech engine is separate. Existing saved recordings are kept.").font(.caption).foregroundStyle(.secondary)
            }
            Section("\(library.profiles.count) imported voice samples") {
                Picker("Category", selection: $category) { ForEach(categories, id: \.self) { Text($0).tag($0) } }
                if library.profiles.isEmpty { Text("Your collection appears here after import. Choose the folder containing collection.json; you do not need to select the JSON file.").foregroundStyle(.secondary) }
                ForEach(filtered) { voice in
                    DisclosureGroup {
                        Button { library.selectedID = voice.id } label: { Label(library.selectedID == voice.id ? "Selected" : "Choose this voice", systemImage: library.selectedID == voice.id ? "checkmark.circle.fill" : "circle") }.disabled(library.busy)
                        Text("Categories: " + voice.categories.joined(separator: ", "))
                        Text("Source: " + voice.source)
                        Text("Permission record: " + voice.permission)
                        Text("Engine: F5TTS_v1_Base · native synthesis not verified yet")
                        Text(library.matchDescription(voice))
                    } label: { Label(voice.name, systemImage: "person.wave.2") }
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
                TextEditor(text: $words).frame(minHeight: 110).accessibilityLabel("Words for your character")
                Button { audio.stop(); library.speak(words, audio: audio, studio: studio) } label: { Label("Create Test Speech", systemImage: "play.fill") }
                    .disabled(library.busy || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse || !library.engineAvailable)
                if !library.engineAvailable { Text("The shared F5 engine is absent from this build. Your imported voice samples remain saved; speech testing becomes available in a build containing that engine.").foregroundStyle(.secondary) }
                Text("Experimental F5 speech. Up to 500 characters per test. This creates new words using the selected reference; it does not convert a recording. Character-match listening and iPhone performance tests are still required.").font(.caption).foregroundStyle(.secondary)
                if let output = library.output, library.outputKind == "speech", library.outputMatchesSelection { AudioActions(url: output) }
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
                    if !library.conversionAvailable { Text("This build needs the shared voice-changing engine before conversion can run.").foregroundStyle(.secondary) }
                    if let source = recorder.output, !recorder.recording { Button("Listen to my original recording") { audio.play(source) }.disabled(library.busy) }
                    Text("Experimental neural voice changing. Character resemblance and iPhone performance require testing; this is not real-time calling.").font(.caption).foregroundStyle(.secondary)
                    if let output = library.output, library.outputKind == "conversion", library.outputMatchesSelection { AudioActions(url: output) }
                }
            }
            Section("Does it sound like your character?") {
                Text("Listen to the reference, then the new speech. Your answer records a listening judgment, separate from technical audio checks.").font(.callout)
                if let selected = library.profiles.first(where: { $0.id == library.selectedID }) {
                    Text("Selected: " + selected.name)
                } else {
                    Text("Open a character above and tap Choose this voice before listening.")
                        .accessibilityIdentifier("character-selection-guidance")
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
        .searchable(text: $search, prompt: "Find a character or category")
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
        .task { await library.loadAndRefresh() }
        .onChange(of: scenePhase) { _, value in if value == .active { Task { await library.loadAndRefresh() } } }
    }
}
