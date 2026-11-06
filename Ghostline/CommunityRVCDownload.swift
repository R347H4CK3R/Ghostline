import SwiftUI
import Foundation
import CryptoKit

/// Exactly pinned external RVC files. No celebrity models, unknown zip
/// contents, or arbitrary URLs are downloaded by this control.
@MainActor
final class GhostlineCommunityRVCDownloader: ObservableObject {
    @Published private(set) var busy = false
    @Published private(set) var percent: Double = 0
    @Published private(set) var received: Int64 = 0
    @Published private(set) var expected: Int64 = 0
    @Published private(set) var speed: Double = 0
    @Published private(set) var phase = "Ready to download"
    @Published private(set) var status = "Download only after reviewing the creator's license and consent."
    private var task: URLSessionDownloadTask?
    let library = RVCPackLibrary()

    var progressLabel: String {
        let a = ByteCountFormatter.string(fromByteCount: received, countStyle: .file)
        let b = ByteCountFormatter.string(fromByteCount: expected, countStyle: .file)
        let rate = ByteCountFormatter.string(fromByteCount: Int64(speed), countStyle: .file)
        return "\(Int(percent * 100))% • \(a) / \(b) • \(rate)/s"
    }

    private struct Asset {
        let name: String
        let source: String
        let sha256: String
        let size: Int64
    }

    private let model = Asset(
        name: "default.pth",
        source: "https://huggingface.co/PhoenixStormJr/RVC-V2-default-voice/resolve/main/default.pth",
        sha256: "c9d6b0ac7aa8df91917757894561cd690e5c4b66e97a9f92630c0a7257fbfccc",
        size: 55_223_136
    )
    private let index = Asset(
        name: "added_IVF511_Flat_nprobe_1_default_v2.index",
        source: "https://huggingface.co/PhoenixStormJr/RVC-V2-default-voice/resolve/main/added_IVF511_Flat_nprobe_1_default_v2.index",
        sha256: "93e0fbf723992b5ff6a1af3cae4e15f3bbb1dd860880fbd76565be23549aa1b7",
        size: 63_016_939
    )

    nonisolated private static func hashFile(_ file: URL) throws -> (String, Int64) {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var h = SHA256()
        var length: Int64 = 0
        while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty {
            length += Int64(data.count)
            h.update(data: data)
        }
        return (h.finalize().map { String(format: "%02x", $0) }.joined(), length)
    }

    private func download(_ asset: Asset, to target: URL, stage: String) async throws {
        guard let url = URL(string: asset.source), url.scheme == "https",
              url.host == "huggingface.co" else { throw URLError(.badURL) }
        phase = stage
        received = 0
        expected = asset.size
        percent = 0
        speed = 0
        let began = Date()
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let transfer = URLSession.shared.downloadTask(with: url) { temporary, response, error in
                do {
                    if let error { throw error }
                    guard let response = response as? HTTPURLResponse,
                          response.statusCode == 200 else {
                        throw URLError(.badServerResponse)
                    }
                    guard let temporary else { throw URLError(.cannotCreateFile) }
                    try FileManager.default.moveItem(at: temporary, to: target)
                    continuation.resume()
                } catch {
                    continuation.resume(throwing: error)
                }
            }
            task = transfer
            transfer.resume()
            Task { @MainActor [weak self] in
                while transfer.state == .running || transfer.state == .suspended {
                    guard let self else { break }
                    self.received = max(0, transfer.countOfBytesReceived)
                    self.expected = asset.size
                    self.percent = min(1, Double(self.received) / Double(asset.size))
                    self.speed = Double(self.received) / max(0.1, Date().timeIntervalSince(began))
                    try? await Task.sleep(for: .milliseconds(250))
                }
            }
        }
        task = nil
        phase = "Verifying SHA-256 before installing"
        let (found, count) = try await Task.detached(priority: .userInitiated) {
            try Self.hashFile(target)
        }.value
        guard count == asset.size, found == asset.sha256 else {
            GhostlineDiagnostics.shared.record("community", "model_checksum_failed")
            throw NSError(domain: "GHOSTLINE.Community", code: 4,
                          userInfo: [NSLocalizedDescriptionKey: "Downloaded file does not match the pinned upstream checksum or size"])
        }
        received = count
        percent = 1
        speed = 0
    }

    func cancel() {
        task?.cancel()
        status = "Cancelling download. Existing model records are preserved."
    }

    /// This only imports checksum-protected CANDIDATES, not verified playable voices.
    func downloadAndImport() async {
        guard !busy else { return }
        if library.packs.contains(where: { $0.weightSHA256 == model.sha256 }) {
            phase = "Already installed"
            status = "This exact RVC model is already imported. Open RVC Packs to use it."
            return
        }
        busy = true
        defer { busy = false; task = nil }
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("ghostline-rvc-" + UUID().uuidString, isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let weight = folder.appendingPathComponent(model.name)
            let retriever = folder.appendingPathComponent(index.name)
            try await download(model, to: weight, stage: "1 of 3 • Downloading RVC model")
            try await download(index, to: retriever, stage: "2 of 3 • Downloading retrieval index")
            phase = "3 of 3 • Importing into private RVC library"
            let priorIDs = Set(library.packs.map(\.id))
            await library.importWeights(weight, name: "Phoenix RVC v2 default (unverified)",
                                        category: "Original test voice",
                                        rights: "Creator-published MIT model card; identity consent and downstream use rights not independently established")
            guard let imported = library.packs.first(where: { !priorIDs.contains($0.id) }) else {
                throw NSError(domain: "GHOSTLINE.Community", code: 5,
                              userInfo: [NSLocalizedDescriptionKey: "Could not add the downloaded model to the private library"])
            }
            await library.attachIndex(retriever, for: imported.id)
            status = library.packs.first(where: { $0.id == imported.id })?.indexFile != nil
                ? "Imported .pth and .index with pinned SHA-256 integrity. This does not verify offline voice conversion."
                : "Imported .pth. The index was not accepted; check RVC Pack Library status."
            phase = "Local candidate ready for converter compatibility testing"
        } catch {
            status = "Download/import stopped: \(error.localizedDescription). Existing imported voices remain unchanged."
            GhostlineDiagnostics.shared.record("community", "model_download_failed")
            phase = "Failed • retriable"
        }
        try? FileManager.default.removeItem(at: folder)
    }
}

struct GhostlineRVCDownloadView: View {
    @StateObject private var downloader = GhostlineCommunityRVCDownloader()
    @State private var licenseReviewed = false
    var body: some View {
        Form {
            Section("Creator-published RVC v2 test voice") {
                Text("Phoenix RVC v2 default voice")
                    .font(.headline)
                Text("Two independently fingerprinted assets: 55.2 MB .pth and 63.0 MB .index. The repository declares MIT. Identity consent, compatibility and full use rights are not independently established.")
                    .font(.footnote).foregroundStyle(.secondary)
                Link("Review original model card and licensing",
                     destination: URL(string: "https://huggingface.co/PhoenixStormJr/RVC-V2-default-voice")!)
                Toggle("I reviewed the creator's terms and have permission to use this model",
                       isOn: $licenseReviewed)
            }
            Section("Download into private RVC library") {
                Text(downloader.phase).font(.subheadline.bold())
                ProgressView(value: downloader.percent, total: 1)
                    .tint(.purple)
                Text(downloader.progressLabel)
                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                if downloader.busy {
                    Button("Cancel download", role: .destructive) { downloader.cancel() }
                } else {
                    Button("Download and import model + index") {
                        Task { await downloader.downloadAndImport() }
                    }
                    .disabled(!licenseReviewed)
                }
                Text(downloader.status).font(.footnote)
                NavigationLink("Open installed RVC voices / converter") {
                    RVCPackLibraryView()
                }
            }
            Section {
                Text("Models are never auto-executed. An imported .pth/.index is an UNVERIFIED candidate; index retrieval remains unimplemented in the current iPhone converter.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .navigationTitle("RVC Download")
    }
}
