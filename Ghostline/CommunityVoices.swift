import SwiftUI
import UniformTypeIdentifiers
import CryptoKit

// Discovery sources are NOT verified playable voices. This local catalog contains
// no remotely fetched identity models or inferred claims of redistribution rights.
private struct CommunitySource: Identifiable {
    let id: String
    let title: String
    let engine: String
    let category: String
    let rights: String
    let summary: String
    let source: String
    let status: String
    let formats: String
    let requiredAction: String
}

private enum CommunitySources {
    static let items: [CommunitySource] = [
        .init(id: "kokoro", title: "Kokoro 82M v1.0", engine: "Kokoro",
              category: "Synthetic TTS", rights: "Apache-2.0 model; check each voice source",
              summary: "54 published voice embeddings across eight languages. These are candidate voice assets, not 54 independently tested iPhone voices.",
              source: "https://huggingface.co/hexgrad/Kokoro-82M",
              status: "Runtime/device verification required", formats: "Voice embeddings and engine assets",
              requiredAction: "Download authorized compatible assets, then test in Kokoro Offline"),
        .init(id: "piper", title: "Piper community model catalog", engine: "Piper",
              category: "Multilingual TTS", rights: "Model-specific license and MODEL_CARD",
              summary: "ONNX voice models in many languages. Review each training dataset and model card before import or redistribution.",
              source: "https://huggingface.co/rhasspy/piper-voices",
              status: "Some models bundled; device verification required", formats: ".onnx + .onnx.json",
              requiredAction: "Use Included Piper Test Voices or Piper Speaker Lab for compatible models"),
        .init(id: "kyutai", title: "Kyutai consented voice donations", engine: "PocketTTS",
              category: "Volunteer reference audio", rights: "CC0 for voice-donations/ subset only",
              summary: "228 consent-based verified submissions, as described by Kyutai. These are recordings, NOT 228 ready-to-run PocketTTS models.",
              source: "https://huggingface.co/kyutai/tts-voices",
              status: "Conditioning/inference not device-verified", formats: ".wav reference clips, some embeddings",
              requiredAction: "Review individual clip license and compatible PocketTTS conditioning pathway"),
        .init(id: "pocket", title: "Pocket TTS runtime", engine: "PocketTTS",
              category: "Synthetic TTS", rights: "Model access conditions; source-specific voice licenses",
              summary: "Efficient neural speech generation and presets. Upstream model access can require accepting terms; no unauthorized automatic downloads.",
              source: "https://huggingface.co/kyutai/pocket-tts",
              status: "Community packs not device-verified", formats: "Model-specific voice state",
              requiredAction: "Review terms and use supported local PocketTTS presets"),
        .init(id: "rvc", title: "Shadowww original RVC voices", engine: "RVC",
              category: "Original creator voices", rights: "CC BY-NC 4.0; attribution and noncommercial use",
              summary: "Four creator-recorded RVC v2 voices, with downloadable .pth/.index pairs and published SHA-256 hashes. No celebrity or film identity implied.",
              source: "https://huggingface.co/ShadowSH2306/shadowww-voices",
              status: "RVC inference/index retrieval not device-verified", formats: ".pth + .index",
              requiredAction: "Download from creator, inspect rights and import into RVC Packs")
    ]
}

private struct LocalCommunityImport: Codable, Identifiable {
    let id: UUID
    let fileName: String
    let sourceID: String
    let sha256: String
    let bytes: Int64
    let importedAt: Date
    let verification: String
}

@MainActor
private final class CommunityImportStore: ObservableObject {
    @Published var items: [LocalCommunityImport] = []
    @Published var status = ""
    @Published var processing = false
    private let directory: URL = FileManager.default.urls(for: .applicationSupportDirectory,
                                                           in: .userDomainMask)[0]
        .appendingPathComponent("CommunityVoiceImports", isDirectory: true)

    init() { load() }

    private var recordsURL: URL { directory.appendingPathComponent("records.json") }

    private func load() {
        guard let data = try? Data(contentsOf: recordsURL),
              let parsed = try? JSONDecoder().decode([LocalCommunityImport].self, from: data)
        else { return }
        items = parsed
    }

    private func save() throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try JSONEncoder().encode(items).write(to: recordsURL, options: [.atomic])
    }

    func importFile(_ external: URL, sourceID: String) async {
        guard !processing else { return }
        processing = true
        defer { processing = false }
        let access = external.startAccessingSecurityScopedResource()
        defer { if access { external.stopAccessingSecurityScopedResource() } }
        do {
            let ext = external.pathExtension.lowercased()
            let supported = ["onnx", "json", "pth", "index", "wav", "bin", "pt"]
            guard supported.contains(ext) else {
                throw NSError(domain: "CommunityVoices", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "Unsupported format. Choose an ONNX, JSON, RVC, WAV or voice-state file."])
            }
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let uid = UUID()
            let target = directory.appendingPathComponent(uid.uuidString + "." + ext)
            try FileManager.default.copyItem(at: external, to: target)
            do {
                // FileHandle streaming prevents copying large model weights into RAM.
                let handle = try FileHandle(forReadingFrom: target)
                defer { try? handle.close() }
                var sha = SHA256()
                var size: Int64 = 0
                while let block = try handle.read(upToCount: 1_048_576), !block.isEmpty {
                    sha.update(data: block)
                    size += Int64(block.count)
                    if Task.isCancelled { throw CancellationError() }
                }
                guard size > 0 else {
                    throw NSError(domain: "CommunityVoices", code: 2,
                                  userInfo: [NSLocalizedDescriptionKey: "The selected file is empty."])
                }
                let hash = sha.finalize().map { String(format: "%02x", $0) }.joined()
                items.insert(.init(id: uid, fileName: external.lastPathComponent,
                                   sourceID: sourceID, sha256: hash, bytes: size,
                                   importedAt: Date(), verification: "CANDIDATE_UNVERIFIED"), at: 0)
                try save()
                status = "Imported and hashed locally. Not installed in an inference engine or verified as a voice."
            } catch {
                try? FileManager.default.removeItem(at: target)
                throw error
            }
        } catch {
            status = "Import failed: \\(error.localizedDescription)"
        }
    }
}

struct GhostlineCommunityVoicesView: View {
    @StateObject private var store = CommunityImportStore()
    @State private var query = ""
    @State private var engine = "All"
    @State private var chosenSource = CommunitySources.items[0].id
    @State private var showingImporter = false
    @State private var rightsAcknowledged = false

    private let filters = ["All", "Piper", "Kokoro", "PocketTTS", "RVC"]
    private var filtered: [CommunitySource] {
        CommunitySources.items.filter {
            (engine == "All" || $0.engine == engine) &&
            (query.isEmpty || "\\($0.title) \\($0.category) \\($0.engine)".localizedCaseInsensitiveContains(query))
        }
    }

    var body: some View {
        List {
            Section {
                Text("Community Voices")
                    .font(.title2.bold())
                    .foregroundStyle(.purple)
                Text("Browse lawful model sources. A download, voice slot or file hash is NOT proof of iPhone speech generation, identity, or voice rights.")
                    .font(.footnote).foregroundStyle(.secondary)
                Label("0 newly device-verified community voices", systemImage: "checkmark.shield")
                    .foregroundStyle(.secondary)
            }
            Section("Discover") {
                Picker("Engine", selection: $engine) {
                    ForEach(filters, id: \.self) { Text($0).tag($0) }
                }
                .pickerStyle(.menu)
                ForEach(filtered) { item in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(item.title).font(.headline)
                            Spacer(minLength: 4)
                            Text(item.engine).font(.caption.bold())
                                .foregroundStyle(.purple)
                        }
                        Text(item.category).font(.caption.weight(.medium))
                        Text(item.summary).font(.subheadline)
                        Label(item.rights, systemImage: "doc.text")
                            .font(.caption).foregroundStyle(.secondary)
                        Label(item.status, systemImage: "exclamationmark.shield")
                            .font(.caption).foregroundStyle(.orange)
                        Text("Format: " + item.formats).font(.caption)
                        Text(item.requiredAction).font(.caption).foregroundStyle(.secondary)
                        if let url = URL(string: item.source) {
                            Link("Official source and license details", destination: url)
                                .font(.subheadline.weight(.semibold))
                        }
                        Button("Choose for local import") { chosenSource = item.id }
                            .buttonStyle(.bordered)
                            .tint(.purple)
                    }
                    .padding(.vertical, 6)
                }
            }
            Section("Private file import") {
                Text("Import only models you are authorized to use. Local imports are checksum-audited candidates; engine compatibility and any licensing or identity permissions remain unverified.")
                    .font(.footnote).foregroundStyle(.secondary)
                Picker("Associated source", selection: $chosenSource) {
                    ForEach(CommunitySources.items) { Text($0.title).tag($0.id) }
                }
                Toggle("I reviewed the source rights and have permission", isOn: $rightsAcknowledged)
                Button("Import local community file") { showingImporter = true }
                    .disabled(!rightsAcknowledged || store.processing)
                if store.processing { ProgressView("Copying and hashing locally…") }
                if !store.status.isEmpty {
                    Text(store.status).font(.footnote).foregroundStyle(.secondary)
                }
            }
            Section("Next: Use a compatible engine") {
                NavigationLink("Piper included / offline test voices") { GhostlineIncludedPiperView() }
                NavigationLink("Kokoro offline studio") { KokoroOfflineView() }
                NavigationLink("PocketTTS voice presets") { NeuralStudioView() }
                NavigationLink("RVC private pack importer") { RVCPackLibraryView() }
                Text("The generic community-file staging area does not automatically attach models to an inference backend. Use the dedicated engine importer for playback tests.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if !store.items.isEmpty {
                Section("Locally staged candidates • \\(store.items.count)") {
                    ForEach(store.items) { item in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.fileName).font(.subheadline.bold())
                            Text(item.verification).font(.caption).foregroundStyle(.orange)
                            Text("SHA-256 " + item.sha256).font(.caption2.monospaced())
                                .textSelection(.enabled)
                            Text(ByteCountFormatter.string(fromByteCount: item.bytes, countStyle: .file))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .searchable(text: $query, prompt: "Search community sources")
        .navigationTitle("Community Voices")
        .fileImporter(isPresented: $showingImporter, allowedContentTypes: [.data, .audio, .json],
                      allowsMultipleSelection: false) { result in
            if case .success(let urls) = result, let first = urls.first {
                let sourceID = chosenSource
                Task { await store.importFile(first, sourceID: sourceID) }
            } else if case .failure(let error) = result {
                // Dismissal does not change the current source selection.
                print("Community file picker: \\(error.localizedDescription)")
            }
        }
    }
}
