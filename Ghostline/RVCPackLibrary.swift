import SwiftUI
import UniformTypeIdentifiers
import CryptoKit

// An imported RVC file is a local candidate, NOT a working iPhone voice.
// Pytorch .pth weights are not directly executable by CoreML or Piper.
struct RVCPackRecord: Identifiable, Codable {
    var id: UUID
    var name: String
    var category: String
    var rightsNote: String
    var weightFile: String
    var weightSHA256: String
    var indexFile: String?
    var indexSHA256: String?
    // Header-only FAISS metadata; nil on legacy catalog entries.
    var indexFamily: String?
    var indexDimension: Int?
    var indexVectorCount: Int64?
    var createdAt: Date
}

@MainActor
final class RVCPackLibrary: ObservableObject {
    @Published var packs: [RVCPackRecord] = []
    @Published var status = "Import authorized RVC v2 .pth weights into a private candidate library. The separate experimental converter is not yet device-verified."
    @Published var busy = false
    @Published var auditReport: URL?

    private var root: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("GHOSTLINE-RVC", isDirectory: true)
    }
    private var indexURL: URL { root.appendingPathComponent("packs.json") }

    init() {
        if let data = try? Data(contentsOf: indexURL),
           let decoded = try? JSONDecoder().decode([RVCPackRecord].self, from: data) {
            packs = decoded.filter { FileManager.default.fileExists(atPath: root.appendingPathComponent($0.weightFile).path) }
        }
    }

    private func digest(_ source: URL) throws -> String {
        let stream = try FileHandle(forReadingFrom: source)
        defer { try? stream.close() }
        var hash = SHA256()
        while true {
            guard let chunk = try stream.read(upToCount: 1024 * 1024), !chunk.isEmpty else { break }
            hash.update(data: chunk)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private func fileBytes(_ url: URL) throws -> UInt64 {
        let attrs = try FileManager.default.attributesOfItem(atPath: url.path)
        return (attrs[.size] as? NSNumber)?.uint64Value ?? 0
    }

    private func copyFromPicker(_ source: URL, to target: URL, allowedExtension: String) throws -> String {
        guard source.pathExtension.lowercased() == allowedExtension else {
            throw NSError(domain: "GHOSTLINE.RVC", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Expected a .\(allowedExtension) file"])
        }
        let permitted = source.startAccessingSecurityScopedResource()
        defer { if permitted { source.stopAccessingSecurityScopedResource() } }
        let size = try fileBytes(source)
        guard size > 1024, size <= 1_000_000_000 else {
            throw NSError(domain: "GHOSTLINE.RVC", code: 2,
                          userInfo: [NSLocalizedDescriptionKey: "File is empty or exceeds the 1 GB import limit"])
        }
        try FileManager.default.copyItem(at: source, to: target)
        return try digest(target)
    }

    func importWeights(_ source: URL, name: String, category: String, rights: String) {
        guard !busy else { return }
        let title = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let authorization = rights.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, !authorization.isEmpty else {
            status = "Enter a title and a genuine source/permission note before importing."
            return
        }
        busy = true
        defer { busy = false }
        let id = UUID()
        let filename = id.uuidString + ".pth"
        let target = root.appendingPathComponent(filename)
        do {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
            let checksum = try copyFromPicker(source, to: target, allowedExtension: "pth")
            let entry = RVCPackRecord(id: id, name: title, category: category,
                                      rightsNote: authorization, weightFile: filename,
                                      weightSHA256: checksum, indexFile: nil,
                                      indexSHA256: nil, indexFamily: nil,
                                      indexDimension: nil, indexVectorCount: nil,
                                      createdAt: Date())
            packs.append(entry)
            do {
                try saveIndex()
            } catch {
                packs.removeAll { $0.id == id }
                throw error
            }
            status = "Imported .pth candidate with SHA-256 integrity. RVC inference and identity have not been verified on this iPhone."
        } catch {
            try? FileManager.default.removeItem(at: target)
            status = "Import failed: \(error.localizedDescription)"
        }
    }

    // Never overwrite the existing retrieval index until its replacement has
    // been copied, hashed and atomically committed to the catalog.
    func attachIndex(_ source: URL, for packID: UUID) {
        guard !busy, let idx = packs.firstIndex(where: { $0.id == packID }) else { return }
        busy = true
        defer { busy = false }
        let previous = packs[idx]
        let filename = packID.uuidString + "-" + UUID().uuidString + ".index"
        let target = root.appendingPathComponent(filename)
        do {
            let checksum = try copyFromPicker(source, to: target, allowedExtension: "index")
            // Fail closed for accidental renames, truncated headers and unknown
            // binary types. This is only a header probe, not FAISS loading.
            let metadata = try GhostlineRVCIndexInspector.inspect(target)
            packs[idx].indexFile = filename
            packs[idx].indexSHA256 = checksum
            packs[idx].indexFamily = metadata.family
            packs[idx].indexDimension = metadata.dimension
            packs[idx].indexVectorCount = metadata.vectorCount
            do {
                try saveIndex()
            } catch {
                packs[idx] = previous
                throw error
            }
            if let old = previous.indexFile, old != filename {
                try? FileManager.default.removeItem(at: root.appendingPathComponent(old))
            }
            auditReport = nil
            status = "FAISS \(metadata.family), \(metadata.dimension)-dim, \(metadata.vectorCount) vectors: candidate header recognized and SHA-256 saved. Retrieval inference remains unavailable."
        } catch {
            packs[idx] = previous
            try? FileManager.default.removeItem(at: target)
            status = "Index import failed without deleting the previous index: \(error.localizedDescription)"
        }
    }

    // JSON contains metadata and checksums, never checkpoint bytes or raw
    // audio. Consent and identity evidence require independent human review.
    func audit(_ pack: RVCPackRecord) {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        auditReport = nil
        do {
            let currentWeightSHA = try digest(root.appendingPathComponent(pack.weightFile))
            let weightMatches = currentWeightSHA == pack.weightSHA256
            var indexMatches: Bool? = nil
            if let indexFile = pack.indexFile {
                guard let expected = pack.indexSHA256 else {
                    throw NSError(domain: "GHOSTLINE.RVC", code: 3,
                                  userInfo: [NSLocalizedDescriptionKey: "Retrieval index has no recorded checksum"])
                }
                indexMatches = try digest(root.appendingPathComponent(indexFile)) == expected
            }
            let indexMetadata: GhostlineRVCIndexInspector.Header? = try pack.indexFile.map {
                try GhostlineRVCIndexInspector.inspect(root.appendingPathComponent($0))
            }
            let metadataMatches = indexMetadata.map {
                (pack.indexFamily == nil || pack.indexFamily == $0.family) &&
                (pack.indexDimension == nil || pack.indexDimension == $0.dimension) &&
                (pack.indexVectorCount == nil || pack.indexVectorCount == $0.vectorCount)
            }
            let report: [String: Any] = [
                "schema_version": 1,
                "record_type": "private_rvc_candidate_file_audit",
                "candidate_id": pack.id.uuidString,
                "display_name": pack.name,
                "category": pack.category,
                "source_and_rights_note_user_supplied": pack.rightsNote,
                "model_sha256": pack.weightSHA256,
                "model_hash_matches": weightMatches,
                "index_sha256": pack.indexSHA256 ?? "",
                "index_hash_matches": indexMatches as Any? ?? NSNull(),
                "index_faiss_header_recognized": indexMetadata != nil,
                "index_header_matches_saved_metadata": metadataMatches as Any? ?? NSNull(),
                "index_family": indexMetadata?.family ?? "",
                "index_dimension": indexMetadata?.dimension as Any? ?? NSNull(),
                "index_vector_count": indexMetadata?.vectorCount as Any? ?? NSNull(),
                "index_retrieval_inference_supported": false,
                "model_inference_on_iphone_verified": false,
                "voice_identity_verified": false,
                "voice_rights_independently_verified": false,
                "generated_utc": ISO8601DateFormatter().string(from: Date())
            ]
            let bytes = try JSONSerialization.data(withJSONObject: report,
                                                   options: [.prettyPrinted, .sortedKeys])
            let file = FileManager.default.temporaryDirectory
                .appendingPathComponent("ghostline-private-rvc-audit-" + pack.id.uuidString + ".json")
            try bytes.write(to: file, options: .atomic)
            auditReport = file
            status = weightMatches && indexMatches != false && metadataMatches != false
                ? "File hashes and candidate FAISS header match. This does not establish usable RVC index retrieval or voice identity."
                : "INTEGRITY FAILURE: a local RVC file or FAISS header differs from its import audit."
        } catch {
            status = "Integrity audit failed: \(error.localizedDescription)"
        }
    }

    private func saveIndex() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try JSONEncoder().encode(packs).write(to: indexURL, options: .atomic)
    }

    func delete(_ pack: RVCPackRecord) {
        guard !busy else { return }
        let previous = packs
        packs.removeAll { $0.id == pack.id }
        do {
            try saveIndex()
            try? FileManager.default.removeItem(at: root.appendingPathComponent(pack.weightFile))
            if let indexFile = pack.indexFile {
                try? FileManager.default.removeItem(at: root.appendingPathComponent(indexFile))
            }
            auditReport = nil
            status = "Pack removed from the private catalog; associated files deleted where possible."
        } catch {
            packs = previous
            status = "Delete not committed; catalog preserved: \(error.localizedDescription)"
        }
    }
}

struct RVCPackLibraryView: View {
    @StateObject private var library = RVCPackLibrary()
    @State private var name = ""
    @State private var category = "Original"
    @State private var rights = ""
    @State private var importWeights = false
    @State private var importIndex = false
    @State private var indexPackID: UUID?
    @State private var packSearch = ""
    @State private var packCategory = "All"
    @FocusState private var editingMetadata: Bool
    private let categories = ["Original", "Licensed character", "Licensed actor", "Licensed singer", "Licensed animation", "Games", "Other"]
    // Search/filter the entire private catalog; no artificial item or result cap.
    private var visiblePacks: [RVCPackRecord] {
        library.packs.filter { pack in
            (packCategory == "All" || pack.category == packCategory) &&
            (packSearch.isEmpty || pack.name.localizedCaseInsensitiveContains(packSearch) ||
             pack.category.localizedCaseInsensitiveContains(packSearch))
        }
    }

    var body: some View {
        Form {
            Section("Private RVC model library") {
                Text("Import RVC .pth model weights and optional .index retrieval files. Imports are local-only and will never be marked functional merely because they exist.")
                    .font(.footnote).foregroundStyle(.secondary)
                TextField("Voice pack name", text: $name)
                    .focused($editingMetadata)
                Picker("Category", selection: $category) {
                    ForEach(categories, id: \.self) { Text($0).tag($0) }
                }
                TextField("Source and rights documentation", text: $rights, axis: .vertical)
                    .lineLimit(2...4)
                    .focused($editingMetadata)
                Button("Import .pth weights") { importWeights = true }
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                              rights.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || library.busy)
            }
            Section("Imported candidates • \(visiblePacks.count) of \(library.packs.count)") {
                TextField("Search private packs", text: $packSearch)
                    .autocorrectionDisabled()
                Picker("Filter category", selection: $packCategory) {
                    Text("All categories").tag("All")
                    ForEach(Array(Set(categories + library.packs.map(\.category))).sorted(), id: \.self) { category in
                        Text(category).tag(category)
                    }
                }
                if library.packs.isEmpty {
                    Text("No imported RVC weights. There are no verified RVC voices on this iPhone.")
                        .foregroundStyle(.secondary)
                }
                ForEach(visiblePacks) { pack in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(pack.name).font(.headline)
                        Text(pack.category + " • Imported, unverified").font(.caption).foregroundStyle(.secondary)
                        Text("SHA-256: " + String(pack.weightSHA256.prefix(16)) + "…")
                            .font(.caption2).monospaced().foregroundStyle(.secondary)
                        Text(pack.indexFile == nil ? "Retrieval index: not attached" :
                             "FAISS candidate: \(pack.indexFamily ?? "legacy/uninspected"), \(pack.indexDimension.map { String($0) } ?? "?") dimensions • retrieval not implemented")
                            .font(.caption)
                        HStack {
                            Button("Attach .index") { indexPackID = pack.id; importIndex = true }
                            Button("Audit SHA-256") { library.audit(pack) }
                            Spacer()
                            Button("Delete", role: .destructive) { library.delete(pack) }
                        }.buttonStyle(.borderless)
                        NavigationLink("Convert with this imported .pth candidate") {
                            GhostlineRVCWebScreen(importedPack: pack)
                        }
                        .font(.subheadline)
                    }
                    .padding(.vertical, 4)
                }
            }
            Section("Conversion compatibility") {
                Label("RVC v2 .pth files stored and hashed", systemImage: "checkmark.seal")
                Label("Experimental local WebAssembly RVC converter included", systemImage: "cpu")
                NavigationLink("Open experimental RVC converter") {
                    GhostlineRVCWebScreen()
                }
                Text("For an imported pack, use its Convert action to load the private .pth candidate directly through an ephemeral SHA-256-checked localhost route. Supply compatible ContentVec ONNX, RMVPE ONNX and source audio separately. A manually chosen .pth/.onnx can override the imported pack. .index retrieval is still not integrated. This path requires actual iPhone/Strata testing.")
                    .font(.footnote).foregroundStyle(.secondary)
                Text(library.status).font(.footnote)
                if let report = library.auditReport {
                    ShareLink(item: report) { Label("Export private file-integrity audit", systemImage: "square.and.arrow.up") }
                    Text("Audit JSON contains your pack name and source/rights note; share only with people you trust.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("RVC Pack Library")
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { editingMetadata = false }
            }
        }
        .fileImporter(isPresented: $importWeights, allowedContentTypes: [.data]) { result in
            if case .success(let url) = result {
                library.importWeights(url, name: name, category: category, rights: rights)
            }
        }
        .fileImporter(isPresented: $importIndex, allowedContentTypes: [.data]) { result in
            if case .success(let url) = result, let pack = indexPackID {
                library.attachIndex(url, for: pack)
            }
        }
    }
}
