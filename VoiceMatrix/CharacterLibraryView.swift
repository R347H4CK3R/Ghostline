import SwiftUI
import UniformTypeIdentifiers

@MainActor final class CharacterLibrary: ObservableObject {
    @Published var profiles: [CharacterReference] = []
    @Published var busy = false
    @Published var selectedID = ""
    @Published var output: URL?
    @Published var message = "Choose your Voices collection folder once. Imported references are copied privately to this iPhone."
    private let store: CharacterFolderStore
    private let engine = F5ReferenceEngine()
    private var job: Task<Void, Never>?
    var engineAvailable: Bool {
        guard let root = Bundle.main.url(forResource: "F5TTS", withExtension: nil) else { return false }
        return FileManager.default.fileExists(atPath: root.appendingPathComponent("voicematrix-engine.json").path)
    }
    init() {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        store = CharacterFolderStore(root: support.appendingPathComponent("CharacterReferences", isDirectory: true))
    }
    func loadAndRefresh() async {
        do { profiles = try await store.profiles() }
        catch { message = error.localizedDescription; return }
        guard !busy, let data = UserDefaults.standard.data(forKey: "characterFolderBookmark.v1") else { return }
        do {
            var stale = false
            let url = try URL(resolvingBookmarkData: data, options: .withoutUI, relativeTo: nil, bookmarkDataIsStale: &stale)
            importFolder(url)
        } catch { message = "The master folder is unavailable. Your imported voices remain on this iPhone. Choose the folder again to refresh it." }
    }
    func importFolder(_ url: URL) {
        guard !busy else { return }
        busy = true; message = "Checking and copying your voices…"
        job = Task {
            let access = url.startAccessingSecurityScopedResource()
            defer { if access { url.stopAccessingSecurityScopedResource() }; busy = false }
            do {
                profiles = try await store.importCollection(at: url)
                // Save access only after the whole collection passes validation.
                if let bookmark = try? url.bookmarkData(options: .minimalBookmark, includingResourceValuesForKeys: nil, relativeTo: nil) {
                    UserDefaults.standard.set(bookmark, forKey: "characterFolderBookmark.v1")
                }
                message = "\(profiles.count) reusable references saved. " + (engineAvailable ? "Choose one to test speech." : "A build containing the shared F5 engine is needed to create speech.") + " Character resemblance has not been verified."
            } catch {
                message = error is CancellationError ? "Import stopped. Previously imported voices were kept." : "Import failed. Previously imported voices were kept. " + error.localizedDescription
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
            message = "This build does not contain the F5 speech engine. Your imported references are safe; install a build containing the shared engine to test speech."; return
        }
        guard let lease = audio.claimProcessing() else { message = "Stop the other recording or speech task first."; return }
        busy = true; message = "Starting the local character speech engine…"
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent("Speech-Character-" + UUID().uuidString + ".wav")
        job = Task {
            defer { busy = false; audio.releaseProcessing(lease) }
            do {
                await studio.releaseModelsForCharacter()
                let reference = try await store.referenceURL(id: voice.id)
                try await engine.load(localBundle: model)
                message = "Creating speech as " + voice.name + "…"
                try await engine.speak(text: text, referenceAudio: reference, referenceText: voice.referenceText, destination: destination)
                try Task.checkCancellation()
                TemporaryAudio.discard(output); output = destination
                message = "Ready to listen, save or share. Please judge the character resemblance by listening; it has not been verified."
            } catch {
                try? FileManager.default.removeItem(at: destination)
                message = error is CancellationError || Task.isCancelled ? "Stopped. Your saved voices were kept." : "Speech could not be created. " + error.localizedDescription
            }
            await engine.unload()
        }
    }
}

struct CharacterLibraryView: View {
    @StateObject private var library = CharacterLibrary()
    @Environment(\.scenePhase) private var scenePhase
    @EnvironmentObject private var audio: AudioStore
    @EnvironmentObject private var studio: SpeechStudio
    @State private var choosing = false
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
                Button { choosing = true } label: { Label("Choose Voices Folder", systemImage: "folder.badge.plus") }
                    .disabled(library.busy).accessibilityIdentifier("import-character-folder")
                Text(library.message).font(.callout).accessibilityAddTraits(.updatesFrequently)
                if library.busy { ProgressView("Working…"); Button("Stop after current step", role: .cancel) { library.cancel() } }
                Text("This imports reusable reference profiles, rather than preview recordings or trained voice-conversion models. Their shared speech engine is separate. Existing saved recordings are kept.").font(.caption).foregroundStyle(.secondary)
            }
            Section("\(library.profiles.count) imported references") {
                Picker("Category", selection: $category) { ForEach(categories, id: \.self) { Text($0).tag($0) } }
                if library.profiles.isEmpty { Text("Your collection appears here after import. Choose the folder containing collection.json; you do not need to select the JSON file.").foregroundStyle(.secondary) }
                ForEach(filtered) { voice in
                    DisclosureGroup {
                        Button { library.selectedID = voice.id } label: { Label(library.selectedID == voice.id ? "Selected" : "Choose this voice", systemImage: library.selectedID == voice.id ? "checkmark.circle.fill" : "circle") }.disabled(library.busy)
                        Text("Categories: " + voice.categories.joined(separator: ", "))
                        Text("Source: " + voice.source)
                        Text("Permission record: " + voice.permission)
                        Text("Engine: F5TTS_v1_Base · native synthesis not verified yet")
                        Text("Character match: awaiting a listening comparison")
                    } label: { Label(voice.name, systemImage: "person.wave.2") }
                }
            }
            Section("Test character speech") {
                Text(library.profiles.first(where: { $0.id == library.selectedID })?.name ?? "Choose an imported character above")
                TextEditor(text: $words).frame(minHeight: 110).accessibilityLabel("Words for your character")
                Button { audio.stop(); library.speak(words, audio: audio, studio: studio) } label: { Label("Create Test Speech", systemImage: "play.fill") }
                    .disabled(library.busy || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse || !library.engineAvailable)
                if !library.engineAvailable { Text("The shared F5 engine is absent from this build. Your imported references remain saved; speech testing becomes available in a build containing that engine.").foregroundStyle(.secondary) }
                Text("Experimental F5 speech. Up to 500 characters per test. This creates new words using the selected reference; it does not convert a recording. Character-match listening and iPhone performance tests are still required.").font(.caption).foregroundStyle(.secondary)
                if let output = library.output { AudioActions(url: output) }
            }
        }
        .navigationTitle("My Character Folder")
        .searchable(text: $search, prompt: "Find a character or category")
        .fileImporter(isPresented: $choosing, allowedContentTypes: [.folder]) { result in
            switch result { case .success(let url): library.importFolder(url)
            case .failure(let error): library.message = "The folder could not be opened. " + error.localizedDescription }
        }
        .task { await library.loadAndRefresh() }
        .onChange(of: scenePhase) { _, value in if value == .active { Task { await library.loadAndRefresh() } } }
    }
}
