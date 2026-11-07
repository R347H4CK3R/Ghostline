import SwiftUI

// Rebuilt iPhone-first interface. The only *selectable Piper TTS models* in
// these views have en_US language metadata. Model metadata is not evidence of
// actual accent, identity, or successful physical-device inference.
enum GhostlineUSVoices {
    static var all: [GhostlineIncludedPiperCatalog.Pack] {
        (GhostlineIncludedPiperCatalog.load()?.models ?? [])
            .filter { $0.language == "en_US" && $0.id.hasPrefix("en_US-") }
            .sorted { $0.display_name.localizedStandardCompare($1.display_name) == .orderedAscending }
    }

    struct Collection: Identifiable {
        let id: String
        let title: String
        let icon: String
        let sample: String
        let detail: String
    }
    static let collections: [Collection] = [
        .init(id: "movies", title: "Movies & Film", icon: "film",
              sample: "The last light faded over the city as our story began.",
              detail: "Original American-English narration, not a licensed film-character voice."),
        .init(id: "tv", title: "Television", icon: "tv",
              sample: "Welcome back. Tonight we have an unexpected announcement.",
              detail: "Original American-English presenter demo, not a television personality."),
        .init(id: "cartoons", title: "Cartoons", icon: "face.smiling",
              sample: "Hey, everybody! We're heading out on an adventure!",
              detail: "An original animated-scene prompt, not a famous cartoon character."),
        .init(id: "anime", title: "Anime", icon: "sparkles",
              sample: "Our greatest adventure is just beginning. We cannot give up.",
              detail: "An American-English animation dub demo, not an authentic anime role."),
        .init(id: "gaming", title: "Gaming", icon: "gamecontroller",
              sample: "Mission control, the objective is secure. Returning to base.",
              detail: "An original game-dialogue prompt, not a recognizable game actor."),
        .init(id: "singers", title: "Singers", icon: "music.mic",
              sample: "Good evening, everyone. Thank you for joining us tonight.",
              detail: "Spoken American-English performance only. Singing is not supported by Piper."),
        .init(id: "celebrities", title: "Celebrities", icon: "star",
              sample: "Thanks for coming. I'm glad we could all be here together.",
              detail: "Original interview-style narration, not a replica of a celebrity."),
        .init(id: "original", title: "Original Voices", icon: "waveform",
              sample: "Hello from Ghostline. This is my original American-English voice.",
              detail: "Original synthetic voices with individually documented model rights.")
    ]
}

private struct GhostlineStudioTile: View {
    let icon: String
    let title: String
    let detail: String
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.title2)
                .frame(width: 48, height: 48)
                .foregroundStyle(Color(red: 0.78, green: 0.54, blue: 1))
                .background(.purple.opacity(0.22), in: RoundedRectangle(cornerRadius: 14))
            VStack(alignment: .leading, spacing: 5) {
                Text(title).font(.headline)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
        }
        .padding(14)
        .background(.white.opacity(0.065), in: RoundedRectangle(cornerRadius: 20))
    }
}

struct GhostlineAmericanRootView: View {
    private let tint = Color(red: 0.68, green: 0.39, blue: 1)
    var body: some View {
        TabView {
            NavigationStack { GhostlineAmericanDashboard() }
                .tabItem { Label("Studio", systemImage: "house.fill") }
            NavigationStack { GhostlineUSVoiceLibrary() }
                .tabItem { Label("Voices", systemImage: "waveform") }
            NavigationStack { GhostlineVoiceChangerView() }
                .tabItem { Label("Changer", systemImage: "mic.fill") }
            NavigationStack { GhostlineAmericanDownloads() }
                .tabItem { Label("Downloads", systemImage: "arrow.down.circle") }
            NavigationStack { GhostlineAmericanSettings() }
                .tabItem { Label("Settings", systemImage: "gearshape.fill") }
        }
        .tint(tint)
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("GhostlineTabbedRoot")
    }
}

struct GhostlineAmericanDashboard: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 15) {
                VStack(alignment: .leading, spacing: 10) {
                    Image(systemName: "waveform.path")
                        .font(.system(size: 52, weight: .semibold))
                        .foregroundStyle(.purple)
                    Text("GHOSTLINE").font(.largeTitle.bold())
                    Text("American Voice Studio").font(.title3.weight(.semibold))
                    Text("Your private, offline-first voice changer and text-to-speech workspace.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    Label("\(GhostlineUSVoices.all.count) bundled American-English model candidates",
                          systemImage: "shippingbox")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(22)
                .background(LinearGradient(colors: [.purple.opacity(0.4),
                                                    .indigo.opacity(0.18), .black],
                                           startPoint: .topLeading, endPoint: .bottomTrailing),
                            in: RoundedRectangle(cornerRadius: 24))
                Text("Create audio").font(.title3.bold())
                NavigationLink {
                    GhostlineUSTextToSpeech()
                } label: {
                    GhostlineStudioTile(icon: "text.bubble.fill",
                                        title: "Text to Speech",
                                        detail: "Type, pick a US English model, generate WAV")
                }.buttonStyle(.plain)
                NavigationLink {
                    GhostlineVoiceChangerView()
                } label: {
                    GhostlineStudioTile(icon: "mic.badge.plus",
                                        title: "Change My Voice",
                                        detail: "Record, select an authorized RVC model, convert")
                }.buttonStyle(.plain)
                Text("Explore").font(.title3.bold())
                NavigationLink {
                    GhostlineUSVoiceLibrary()
                } label: {
                    GhostlineStudioTile(icon: "square.grid.2x2.fill",
                                        title: "Voice Categories",
                                        detail: "Eight American-English creative demo groups")
                }.buttonStyle(.plain)
                NavigationLink {
                    GhostlineAmericanDownloads()
                } label: {
                    GhostlineStudioTile(icon: "arrow.down.circle",
                                        title: "Voice Downloads",
                                        detail: "Community models, permissions, progress and hashes")
                }.buttonStyle(.plain)
                Text("An included voice is not 'verified' until it creates audible offline speech on the target iPhone and is reviewed. No character, singer or celebrity identity is verified.")
                    .font(.footnote).foregroundStyle(.secondary)
                    .padding(12)
            }
            .padding(18)
        }
        .navigationTitle("Studio")
    }
}

struct GhostlineUSVoiceLibrary: View {
    var body: some View {
        List {
            Section {
                Text("American English only").font(.headline).foregroundStyle(.purple)
                Text("The active TTS voice picker uses en_US models exclusively. A category describes a creative usage, not a person's voice identity.")
                    .font(.footnote).foregroundStyle(.secondary)
                Text("\(GhostlineUSVoices.all.count) source-reviewed models • 0 device-verified identities")
                    .font(.caption)
            }
            Section("Browse categories") {
                ForEach(GhostlineUSVoices.collections) { collection in
                    NavigationLink {
                        GhostlineUSTextToSpeech(collection: collection)
                    } label: {
                        Label(collection.title, systemImage: collection.icon)
                    }
                }
            }
            Section("All American-English TTS models") {
                ForEach(GhostlineUSVoices.all) { voice in
                    NavigationLink {
                        GhostlineUSTextToSpeech(initialModelID: voice.id)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(voice.display_name).font(.headline)
                            Text("en_US • source-reviewed • iPhone audio unverified")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Section("More") {
                NavigationLink("Private RVC voice changer") { GhostlineVoiceChangerView() }
            }
        }
        .navigationTitle("Voices")
    }
}

struct GhostlineUSTextToSpeech: View {
    var collection: GhostlineUSVoices.Collection? = nil
    var initialModelID: String? = nil
    @StateObject private var studio = GhostlineIncludedPiperStudio()
    @State private var phrase = "Welcome to Ghostline. This is an American-English synthetic voice."

    var body: some View {
        Form {
            Section("1 · Choose a voice") {
                if let collection {
                    Text(collection.detail).font(.footnote).foregroundStyle(.secondary)
                }
                Picker("American-English voice", selection: Binding(
                    get: { studio.selectedID },
                    set: { studio.selectPack($0) })) {
                    ForEach(GhostlineUSVoices.all) { voice in
                        Text(voice.display_name).tag(voice.id)
                    }
                }
                .disabled(studio.busy || GhostlineUSVoices.all.isEmpty)
                if let voice = studio.chosen,
                   GhostlineUSVoices.all.contains(where: { $0.id == voice.id }) {
                    Text("Model: \(voice.id) · \(voice.language)")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("Training: \(voice.training_lineage)")
                        .font(.caption).foregroundStyle(.secondary)
                    if let url = URL(string: voice.model_card_url) {
                        Link("Review model card & permissions", destination: url)
                    }
                }
            }
            Section("2 · Type what to say") {
                TextEditor(text: $phrase).frame(minHeight: 100)
                Button {
                    Task { await studio.generate(phrase) }
                } label: {
                    Label(studio.busy ? "Generating offline audio…" : "Generate American-English Speech",
                          systemImage: "waveform")
                }
                .buttonStyle(.borderedProminent).tint(.purple)
                .disabled(studio.busy || phrase.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                          !GhostlineUSVoices.all.contains(where: { $0.id == studio.selectedID }))
                if studio.busy { ProgressView("Checking model and synthesizing") }
            }
            Section("3 · Listen and export") {
                if let wav = studio.outputURL {
                    Button("Replay generated WAV") { studio.replaySavedWAV() }
                        .disabled(studio.busy)
                    ShareLink(item: wav) {
                        Label("Export WAV", systemImage: "square.and.arrow.up")
                    }
                    Button("I heard the full recording") { studio.attestListening() }
                        .disabled(studio.busy || !studio.playbackCompleted || studio.userAttestedListening)
                    Button("Prepare private verification receipt") { studio.exportEvidence() }
                    if let receipt = studio.evidenceURL {
                        ShareLink(item: receipt) { Text("Export device test receipt") }
                    }
                } else {
                    Text("Generated audio will appear here when the on-device engine succeeds.")
                        .foregroundStyle(.secondary)
                }
            }
            Section("Diagnostics and verification") {
                Text(studio.status).font(.footnote)
                Button("Export local generation diagnostics") { studio.exportDiagnostics() }
                    .disabled(studio.busy)
                if let diagnostics = studio.diagnosticURL {
                    ShareLink(item: diagnostics) {
                        Label("Export local error details", systemImage: "doc.text")
                    }
                }
                Text("Model availability and CI builds do not prove an American accent, audible synthesis or authorized actor identity. All remain unverified until physical-device evidence.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle(collection?.title ?? "Text to Speech")
        .onAppear {
            phrase = collection?.sample ?? phrase
            let valid = GhostlineUSVoices.all
            let requested = initialModelID.flatMap { key in valid.first(where: { $0.id == key }) }
            if let voice = requested ?? valid.first, studio.selectedID != voice.id {
                studio.selectPack(voice.id)
            }
        }
    }
}

struct GhostlineAmericanDownloads: View {
    var body: some View {
        List {
            Section("Included American English") {
                Text("\(GhostlineUSVoices.all.count) en_US model candidates included with this test build.")
                Text("Additional languages remain in earlier experimental builds; the new Studio and Voices tabs show American-English TTS models only.")
                    .font(.caption).foregroundStyle(.secondary)
                NavigationLink("Test included US voice models") { GhostlineUSTextToSpeech() }
            }
            Section("Community voice models") {
                NavigationLink("Rights-reviewed community catalog") { GhostlineCommunityVoicesView() }
                NavigationLink("Browse 589 three-provider model listings") {
                    GhostlineThreeSourceCatalogView()
                }
                NavigationLink("Download creator-published RVC weights") { GhostlineRVCDownloadView() }
                NavigationLink("Manage private RVC voice packs") { RVCPackLibraryView() }
                Text("Some downloads require model-specific licenses. American-English accent and actual device compatibility are not confirmed by an RVC file's name.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.navigationTitle("Downloads")
    }
}

struct GhostlineAmericanSettings: View {
    var body: some View {
        Form {
            Section("Privacy and diagnostics") {
                NavigationLink("Private live error diagnostics") { GhostlineDiagnosticsView() }
                Text("Error uploads are opt-in. No microphone audio or model files are sent to GitHub.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Advanced engines") {
                NavigationLink("American-English Text to Speech") { GhostlineUSTextToSpeech() }
                NavigationLink("Private RVC Packs") { RVCPackLibraryView() }
                NavigationLink("RVC Core ML Experiment") { RVCCoreMLModelView() }
                Text("Non-American Piper and multilingual legacy engines are excluded from the rebuilt voice selectors.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("About") {
                Text("GHOSTLINE · American-English Studio")
                Text("5-tab interface · offline-first · expandable model library")
                Text("Voice and identity verification: not established on physical iPhone/Strata.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.navigationTitle("Settings")
    }
}
