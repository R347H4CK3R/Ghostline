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
    @Published var status = "Import locally owned RVC v2 .pth weights. This builds a private catalog; conversion is not yet implemented on iOS."
    @Published var busy = false

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
            try saveIndex()
            status = "Imported .pth candidate with SHA-256 integrity. RVC inference and identity have not been verified on this iPhone."
        } catch {
            try? FileManager.default.removeItem(at: target)
            status = "Import failed: \(error.localizedDescription)"
        }
    }

    func attachIndex(_ source: URL, for packID: UUID) {
        guard !busy, let idx = packs.firstIndex(where: { $0.id == packID }) else { return }
        busy = true
        defer { busy = false }
        let filename = packID.uuidString + ".index"
        let target = root.appendingPathComponent(filename)
        do {
            try? FileManager.default.removeItem(at: target)
            let checksum = try copyFromPicker(source, to: target, allowedExtension: "index")
            packs[idx].indexFile = filename
            packs[idx].indexSHA256 = checksum
            try saveIndex()
            status = "Attached retrieval index. This does not establish device inference support."
        } catch {
            status = "Index import failed: \(error.localizedDescription)"
        }
    }

    private func saveIndex() throws {
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try JSONEncoder().encode(packs).write(to: indexURL, options: .atomic)
    }

    func delete(_ pack: RVCPackRecord) {
        try? FileManager.default.removeItem(at: root.appendingPathComponent(pack.weightFile))
        if let indexFile = pack.indexFile {
            try? FileManager.default.removeItem(at: root.appendingPathComponent(indexFile))
        }
        packs.removeAll { $0.id == pack.id }
        do { try saveIndex(); status = "Pack deleted from private app storage." }
        catch { status = "Files deleted; catalog index could not be written." }
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
                        Text("SHA-256: " + pack.weightSHA256.prefix(16) + "…")
                            .font(.caption2).monospaced().foregroundStyle(.secondary)
                        Text(pack.indexFile == nil ? "Retrieval index: not attached" : "Retrieval index: attached")
                            .font(.caption)
                        HStack {
                            Button("Attach .index") { indexPackID = pack.id; importIndex = true }
                            Spacer()
                            Button("Delete", role: .destructive) { library.delete(pack) }
                        }.buttonStyle(.borderless)
                    }
                    .padding(.vertical, 4)
                }
            }
            Section("Conversion compatibility") {
                Label("RVC v2 .pth files stored and hashed", systemImage: "checkmark.seal")
                Label("Offline RVC runtime not yet available in this iOS build", systemImage: "exclamationmark.triangle")
                Text("A .pth file uses PyTorch serialization. Ghostline must add a compatible on-device runtime or a validated CoreML conversion before it can perform RVC voice conversion; importing is not a playback test.")
                    .font(.footnote).foregroundStyle(.secondary)
                Text(library.status).font(.footnote)
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
