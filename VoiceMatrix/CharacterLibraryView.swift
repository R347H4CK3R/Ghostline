import SwiftUI
import UniformTypeIdentifiers

@MainActor final class CharacterLibrary: ObservableObject {
    @Published var profiles: [CharacterReference] = []
    @Published var busy = false
    @Published var message = "Choose your Voices collection folder once. Imported references are copied privately to this iPhone."
    private let store: CharacterFolderStore
    private var job: Task<Void, Never>?
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
                message = "\(profiles.count) reusable references saved. These need the compatible F5 engine before speech can be created. Character resemblance has not been verified."
            } catch {
                message = error is CancellationError ? "Import stopped. Previously imported voices were kept." : "Import failed. Previously imported voices were kept. " + error.localizedDescription
            }
        }
    }
    func cancel() { job?.cancel() }
}

struct CharacterLibraryView: View {
    @StateObject private var library = CharacterLibrary()
    @Environment(\.scenePhase) private var scenePhase
    @State private var choosing = false
    @State private var search = ""
    @State private var category = "All"
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
                if library.busy { ProgressView("Importing voices…"); Button("Cancel", role: .cancel) { library.cancel() } }
                Text("This imports reusable reference profiles, rather than preview recordings or trained voice-conversion models. Their shared speech engine is separate. Existing saved recordings are kept.").font(.caption).foregroundStyle(.secondary)
            }
            Section("\(library.profiles.count) imported references") {
                Picker("Category", selection: $category) { ForEach(categories, id: \.self) { Text($0).tag($0) } }
                if library.profiles.isEmpty { Text("Your collection appears here after import. Choose the folder containing collection.json; you do not need to select the JSON file.").foregroundStyle(.secondary) }
                ForEach(filtered) { voice in
                    DisclosureGroup {
                        Text("Categories: " + voice.categories.joined(separator: ", "))
                        Text("Source: " + voice.source)
                        Text("Permission record: " + voice.permission)
                        Text("Engine: F5TTS_v1_Base · native synthesis not verified yet")
                        Text("Character match: awaiting a listening comparison")
                    } label: { Label(voice.name, systemImage: "person.wave.2") }
                }
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
