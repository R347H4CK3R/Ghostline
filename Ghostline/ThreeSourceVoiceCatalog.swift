import SwiftUI
import Foundation

/// Cross-directory browsing metadata. A listed source is not a bundled model,
/// permission to imitate anyone, or verified offline speech on the target iPhone.
private struct GhostlineSourceSnapshot: Decodable {
    struct Entry: Identifiable, Decodable {
        let id: String
        let provider: String
        let name: String
        let category: String
        let engine: String
        let license: String
        let url: String
        let summary: String
        let availability: String
        let downloaded: Bool
        let device_verified: Bool
        let identity_verified: Bool
        let redistribution_rights_verified: Bool
    }
    let schema_version: Int
    let generated_utc: String
    let catalog_scope: String
    let warning: String
    let entries: [Entry]
    static func load() -> GhostlineSourceSnapshot? {
        guard let url = Bundle.main.url(forResource: "three-source-catalog", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let result = try? JSONDecoder().decode(GhostlineSourceSnapshot.self, from: data),
              result.schema_version == 1 else { return nil }
        return result
    }
}


/// Five additional external discovery directories, not preinstalled voice packs.
/// "Horror" and "Animation" are search priorities, not verified model identities.
private struct GhostlineAdditionalSource: Identifiable {
    let id: String
    let title: String
    let url: String
    let emphasis: String
    let classification: String
    let limitation: String
    static let all: [Self] = [
        .init(id: "voice-models", title: "Voice Models — RVC directory",
              url: "https://voice-models.com/",
              emphasis: "Horror, game characters, animation, singers",
              classification: "Community RVC download links",
              limitation: "Creator links and vocal likeness rights require review; no models automatically installed."),
        .init(id: "rvcvoicemodels", title: "RVC Voice Models — community hub",
              url: "https://rvcvoicemodels.com/",
              emphasis: "Characters, animation, voice-conversion demos",
              classification: "Creator-uploaded RVC v2 listings",
              limitation: "Community uploads do not establish impersonation consent or iPhone compatibility."),
        .init(id: "fakeyou", title: "FakeYou — voice-to-voice directory",
              url: "https://fakeyou.com/voice-conversion",
              emphasis: "Cartoon and movie-character voice demonstrations",
              classification: "Hosted community voice-conversion models",
              limitation: "Hosted access does not grant downloadable offline model weights or redistribution rights."),
        .init(id: "weightsai", title: "Weights AI — community voices",
              url: "https://weightsai.net/voices",
              emphasis: "Animation, gaming and singer-inspired community models",
              classification: "Community RVC voice library",
              limitation: "Unofficial fan uploads; check source provenance and individual permissions."),
        .init(id: "aihub", title: "AI Hub — RVC model forum guide",
              url: "https://docs.aihub.gg/essentials/voice-models/",
              emphasis: "Community model discovery and .pth/.index guidance",
              classification: "Community directory and instructional resource",
              limitation: "The guide is not a voice pack; external creator files need independent vetting.")
    ]
}

struct GhostlineThreeSourceCatalogView: View {
    @State private var search = ""
    @State private var selectedProvider = "All"
    @State private var selectedCategory = "All"
    @State private var showOnlyDeclaredLicenses = false
    @State private var directoryPriority = "All"
    private let snapshot = GhostlineSourceSnapshot.load()
    private let providers: [(String, String)] = [
        ("All", "All sources"), ("aivoices", "AI Voices"),
        ("huggingface", "Hugging Face"), ("openvoice", "OpenVoice V2")
    ]
    private var categories: [String] {
        ["All"] + Array(Set(snapshot?.entries.map(\.category) ?? [])).sorted()
    }
    private var filtered: [GhostlineSourceSnapshot.Entry] {
        guard let snapshot else { return [] }
        return snapshot.entries.filter { item in
            (selectedProvider == "All" || item.provider == selectedProvider) &&
            (selectedCategory == "All" || item.category == selectedCategory) &&
            (!showOnlyDeclaredLicenses || (item.license != "not declared" &&
                                          item.license != "unknown" &&
                                          item.license != "source review required")) &&
            (search.isEmpty || [item.name,item.category,item.engine,item.license,item.provider]
                .joined(separator: " ").localizedCaseInsensitiveContains(search))
        }
    }
    var body: some View {
        List {
            Section {
                Text("Three-Source Discovery")
                    .font(.title2.bold()).foregroundStyle(.purple)
                Text("Browse AIVoices, Hugging Face and OpenVoice V2. Results are a local snapshot of source listings, not installed voice files.")
                    .font(.footnote).foregroundStyle(.secondary)
                Label("\(snapshot?.entries.count ?? 0) indexed source entries · 0 newly iPhone-verified voices",
                      systemImage: "magnifyingglass")
                    .font(.caption).foregroundStyle(.secondary)
                Text("AIVoices lists many external models; OpenVoice V2 is an engine, not a catalog of celebrity recordings. Individual usage rights, identity consent and offline compatibility remain unverified.")
                    .font(.caption).foregroundStyle(.orange)
            }
            Section("Filters") {
                Picker("Source", selection: $selectedProvider) {
                    ForEach(providers.indices, id: \.self) { index in
                        Text(providers[index].1).tag(providers[index].0)
                    }
                }
                Picker("Category", selection: $selectedCategory) {
                    ForEach(categories, id: \.self) { Text($0).tag($0) }
                }
                Toggle("Show entries with declared model-license labels", isOn: $showOnlyDeclaredLicenses)
                Text("A model-license label does not prove that the model's training speaker consented to cloning or redistribution.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Catalog listings · \(filtered.count)") {
                if filtered.isEmpty {
                    Text("No entries match the selected filters. Change the search or source.")
                        .foregroundStyle(.secondary)
                }
                ForEach(filtered) { item in
                    VStack(alignment: .leading, spacing: 7) {
                        HStack(alignment: .top) {
                            Text(item.name).font(.headline)
                            Spacer(minLength: 5)
                            Text(item.provider == "aivoices" ? "AI Voices" :
                                 item.provider == "huggingface" ? "HF" : "Engine")
                                .font(.caption.bold()).foregroundStyle(.purple)
                        }
                        Text(item.category + " · " + item.engine)
                            .font(.subheadline).foregroundStyle(.secondary)
                        Label("Discovery only · no verified offline audio", systemImage: "exclamationmark.shield")
                            .font(.caption).foregroundStyle(.orange)
                        Text("Source rights: " + item.license)
                            .font(.caption).foregroundStyle(.secondary)
                        if let url = URL(string: item.url), url.scheme == "https" {
                            Link("Open original model listing and review terms", destination: url)
                                .font(.subheadline.weight(.semibold))
                        }
                    }
                    .padding(.vertical, 6)
                }
            }
            Section("Five additional model sources") {
                Text("Prioritized for cartoons, animated characters, and horror-film-style voices. These are external directories, not five preinstalled model packs.")
                    .font(.caption).foregroundStyle(.secondary)
                Picker("Discovery focus", selection: $directoryPriority) {
                    Text("All").tag("All")
                    Text("Animation").tag("Animation")
                    Text("Horror & movies").tag("Horror & movies")
                }
                .pickerStyle(.menu)
                ForEach(GhostlineAdditionalSource.all.filter { entry in
                    directoryPriority == "All" ||
                    (directoryPriority == "Animation" &&
                     ["voice-models", "rvcvoicemodels", "fakeyou", "weightsai", "aihub"].contains(entry.id)) ||
                    (directoryPriority == "Horror & movies" &&
                     ["voice-models", "rvcvoicemodels", "fakeyou", "weightsai", "aihub"].contains(entry.id))
                }) { source in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(source.title).font(.headline)
                        Text(source.emphasis).font(.subheadline)
                        Text(source.classification).font(.caption).foregroundStyle(.secondary)
                        Text(source.limitation).font(.caption).foregroundStyle(.orange)
                        if let url = URL(string: source.url) {
                            Link("Browse source", destination: url)
                        }
                    }.padding(.vertical, 5)
                }
                Text("The discovery focus is an editorial guide. No horror or character model is claimed authentic until its reference, permission, and actual offline output are checked.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Browse complete provider directories") {
                Link("AI Voices — full community model directory",
                     destination: URL(string: "https://aivoices.gg/models")!)
                Link("Hugging Face — complete model directory",
                     destination: URL(string: "https://huggingface.co/models")!)
                Link("OpenVoice V2 — official engine weights and license",
                     destination: URL(string: "https://huggingface.co/myshell-ai/OpenVoiceV2")!)
                Text("The local snapshot is a bounded, searchable offline index. The provider links access their full live directories when connected. OpenVoice V2 is an engine, not thousands of prepackaged voices.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Using a permitted voice pack") {
                NavigationLink("Import private RVC .pth / .index pack") { RVCPackLibraryView() }
                NavigationLink("Open offline RVC converter") { GhostlineRVCWebScreen() }
                NavigationLink("Open offline PocketTTS") { NeuralStudioView() }
                Text("No external listing is automatically downloaded or run. Obtain the right to use each voice, import it into a compatible engine and verify real audio on this iPhone.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
        .searchable(text: $search, prompt: "Search models, voices, artists and frameworks")
        .navigationTitle("Model Discovery")
        .navigationBarTitleDisplayMode(.inline)
        .scrollDismissesKeyboard(.interactively)
    }
}
