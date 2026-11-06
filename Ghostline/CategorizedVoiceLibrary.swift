import SwiftUI

/// A category is an editorial browsing group, not a claim that any model
/// reproduces an actor, performer, movie character or intellectual property.
struct GhostlineVoiceCategory: Identifiable {
    let id: String
    let title: String
    let symbol: String
    let modelIDs: [String]
    let description: String
    static let all: [Self] = [
        .init(id: "film", title: "Movies & film", symbol: "film",
              modelIDs: ["en_GB-cori-medium", "en_US-norman-medium"],
              description: "Original narrative speech demos — not licensed film-character replicas."),
        .init(id: "television", title: "Television", symbol: "tv",
              modelIDs: ["en_US-kristin-medium"],
              description: "Synthetic presenter/dialogue demo — not an identifiable TV performer."),
        .init(id: "cartoons", title: "Cartoons", symbol: "face.smiling",
              modelIDs: ["nl_BE-rdh-medium", "nl_BE-rdh-x_low"],
              description: "Original cartoon-scene demo voices — no character-identity claims."),
        .init(id: "anime", title: "Anime", symbol: "sparkles",
              modelIDs: ["uk_UA-ukrainian_tts-medium"],
              description: "Original animation-scene demos, not named anime voice actors."),
        .init(id: "gaming", title: "Gaming", symbol: "gamecontroller",
              modelIDs: ["no_NO-nvcc-medium"],
              description: "Original game-dialogue samples — not an existing game character."),
        .init(id: "singers", title: "Singers", symbol: "music.mic",
              modelIDs: ["es_ES-carlfm-x_low"],
              description: "Spoken performance demo only. These models are TTS, not singing synthesis."),
        .init(id: "celebrities", title: "Celebrities", symbol: "star",
              modelIDs: ["nl_BE-nathalie-x_low"],
              description: "Original interview-style demo, with no celebrity impersonation."),
        .init(id: "original", title: "Original voices", symbol: "waveform",
              modelIDs: ["en_US-ljspeech-medium", "el_GR-rapunzelina-medium"],
              description: "Open-license synthetic voices with published model provenance.")
    ]
}

struct GhostlineCategorizedVoiceLibraryView: View {
    private let catalog = GhostlineIncludedPiperCatalog.load()
    private var available: [GhostlineIncludedPiperCatalog.Pack] { catalog?.models ?? [] }
    var body: some View {
        List {
            Section {
                Label("Voice Library", systemImage: "waveform")
                    .font(.title2.bold()).foregroundStyle(.purple)
                Text("Choose a category and generate actual offline speech using its included Piper voice models. The category is a demonstration style, not the voice identity.")
                    .font(.subheadline)
                Label("\(available.count) packaged Piper model candidates", systemImage: "shippingbox")
                Label("0 target-iPhone identity-verified voices", systemImage: "checkmark.shield")
                    .foregroundStyle(.secondary)
                Text("Each model is source-documented, but it becomes device-verified only after offline audio, completed playback and human review. No actor, cartoon, TV, game or singer identity is authenticated by these model names.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Choose a category") {
                ForEach(GhostlineVoiceCategory.all) { category in
                    NavigationLink {
                        GhostlineCategoryTTSView(category: category)
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: category.symbol)
                                .frame(width: 30).foregroundStyle(.purple)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(category.title).font(.headline)
                                let count = available.filter { category.modelIDs.contains($0.id) }.count
                                Text("\(count) included synthetic voice model\(count == 1 ? "" : "s") • unverified")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
            Section("Voice changer") {
                NavigationLink("Record and change your voice with RVC") {
                    GhostlineVoiceChangerView()
                }
                Text("Piper category voices support local text-to-speech. RVC conversion uses separate authorized RVC models. This build does not automatically turn Piper models into RVC checkpoints.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("More models") {
                NavigationLink("Community Voices and downloads") {
                    GhostlineCommunityVoicesView()
                }
                NavigationLink("Browse all bundled Piper voices") {
                    GhostlineIncludedPiperView()
                }
            }
        }
        .navigationTitle("Voice Library")
    }
}

struct GhostlineCategoryTTSView: View {
    let category: GhostlineVoiceCategory
    @StateObject private var studio = GhostlineIncludedPiperStudio()
    @State private var words = "This is a Ghostline original synthetic voice test."
    private var eligible: [GhostlineIncludedPiperCatalog.Pack] {
        studio.candidates.filter { category.modelIDs.contains($0.id) }
    }
    var body: some View {
        Form {
            Section(category.title) {
                Text(category.description)
                    .font(.subheadline).foregroundStyle(.secondary)
                Text("Candidate synthetic voices, not authentic entertainment or performer replicas.")
                    .font(.caption).foregroundStyle(.orange)
            }
            Section("1 · Choose a voice model") {
                if eligible.isEmpty {
                    Text("No matching bundled models in this build.")
                } else {
                    ForEach(eligible) { pack in
                        Button {
                            studio.selectPack(pack.id)
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(pack.display_name).font(.headline)
                                    Text("\(pack.language) · \(pack.speaker_ids.count) candidate slot(s)")
                                        .font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if studio.selectedID == pack.id {
                                    Image(systemName: "checkmark.circle.fill").foregroundStyle(.purple)
                                }
                            }
                        }
                        .disabled(studio.busy)
                    }
                }
                if let pack = studio.chosen, eligible.contains(where: { $0.id == pack.id }) {
                    Text("License: \(pack.license)").font(.caption)
                    Text("Training: \(pack.training_lineage)")
                        .font(.caption).foregroundStyle(.secondary)
                    if let url = URL(string: pack.model_card_url) {
                        Link("Original voice model card and rights", destination: url)
                    }
                    if pack.speaker_ids.count > 1 {
                        Picker("Speaker slot", selection: Binding(
                            get: { studio.selectedSpeakerID },
                            set: { studio.selectSpeaker($0) })) {
                                ForEach(pack.speaker_ids, id: \.self) { speaker in
                                    Text("Candidate \(speaker)").tag(speaker)
                                }
                            }
                    }
                }
            }
            Section("2 · Offline text-to-speech") {
                TextEditor(text: $words).frame(minHeight: 90)
                Button(studio.busy ? "Generating…" : "Generate and play selected voice") {
                    Task { await studio.generate(words) }
                }
                .buttonStyle(.borderedProminent)
                .tint(.purple)
                .disabled(studio.busy || !eligible.contains(where: { $0.id == studio.selectedID }))
                if let wav = studio.outputURL {
                    Button("Replay recorded WAV") { studio.replaySavedWAV() }
                        .disabled(studio.busy)
                    ShareLink(item: wav) {
                        Label("Export generated WAV", systemImage: "square.and.arrow.up")
                    }
                    Button("I listened to the entire WAV") { studio.attestListening() }
                        .disabled(studio.busy || !studio.playbackCompleted || studio.userAttestedListening)
                    Button("Prepare SHA-256 evidence") { studio.exportEvidence() }
                    if let evidence = studio.evidenceURL {
                        ShareLink(item: evidence) { Text("Export private test evidence") }
                    }
                }
            }
            Section("3 · Change recorded speech") {
                NavigationLink("Open RVC Voice Changer") { GhostlineVoiceChangerView() }
                Text("A TTS sample and an RVC voice conversion are different workflows. Use an authorized RVC model in Voice Changer.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Device status") {
                Text(studio.status).font(.footnote)
                Text("Device offline isolation, perceptual identity and voice usage permissions have not been independently verified.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle(category.title)
        .onAppear {
            if let first = eligible.first, !eligible.contains(where: { $0.id == studio.selectedID }) {
                studio.selectPack(first.id)
            }
        }
    }
}
