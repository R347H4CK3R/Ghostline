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
                                      indexSHA256: nil, createdAt: Date())
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
            packs[idx].indexFile = filename
            packs[idx].indexSHA256 = checksum
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
            status = "Retrieval index saved with SHA-256. Conversion and iPhone inference remain unverified."
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
            status = weightMatches && indexMatches != false
                ? "File integrity matches import checksums. This is not proof of authorized voice or working RVC audio."
                : "INTEGRITY FAILURE: a local RVC file differs from its import checksum."
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
    private let categories = ["Original", "Licensed character", "Licensed actor", "Licensed singer", "Licensed animation", "Games", "Other"]

    var body: some View {
        Form {
            Section("Private RVC model library") {
                Text("Import RVC .pth model weights and optional .index retrieval files. Imports are local-only and will never be marked functional merely because they exist.")
                    .font(.footnote).foregroundStyle(.secondary)
                TextField("Voice pack name", text: $name)
                Picker("Category", selection: $category) {
                    ForEach(categories, id: \.self) { Text($0).tag($0) }
                }
                TextField("Source and rights documentation", text: $rights, axis: .vertical)
                    .lineLimit(2...4)
                Button("Import .pth weights") { importWeights = true }
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                              rights.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || library.busy)
            }
            Section("Imported candidates • \(library.packs.count)") {
                if library.packs.isEmpty {
                    Text("No imported RVC weights. There are no verified RVC voices on this iPhone.")
                        .foregroundStyle(.secondary)
                }
                ForEach(library.packs) { pack in
                    VStack(alignment: .leading, spacing: 5) {
                        Text(pack.name).font(.headline)
                        Text(pack.category + " • Imported, unverified").font(.caption).foregroundStyle(.secondary)
                        Text("SHA-256: " + String(pack.weightSHA256.prefix(16)) + "…")
                            .font(.caption2).monospaced().foregroundStyle(.secondary)
                        Text(pack.indexFile == nil ? "Retrieval index: not attached" : "Retrieval index: attached")
                            .font(.caption)
                        HStack {
                            Button("Attach .index") { indexPackID = pack.id; importIndex = true }
                            Button("Audit SHA-256") { library.audit(pack) }
                            Spacer()
                            Button("Delete", role: .destructive) { library.delete(pack) }
                        }.buttonStyle(.borderless)
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
                Text("Conversion requires separately selecting a compatible RVC v2 .pth/.onnx voice model, ContentVec ONNX, RMVPE ONNX and source audio. Imported library weights do not automatically load into the converter; .index retrieval is not integrated. A compiled runtime does not prove conversion works on this iPhone.")
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
