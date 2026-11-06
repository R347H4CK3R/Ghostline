import SwiftUI
import UniformTypeIdentifiers
import CryptoKit
import OnnxRuntimeBindings

/// Validates ONNX graph loading locally on iOS. This is NOT an RVC audio converter.
@MainActor
final class RVCOnnxRuntimeLab: ObservableObject {
    @Published var status = "Import a legally usable ONNX model to test runtime compatibility offline."
    @Published var modelName: String?
    @Published var graphInputs: [String] = []
    @Published var graphOutputs: [String] = []
    @Published var sha256: String?
    @Published var busy = false
    @Published var graphLoaded = false
    private var session: ORTSession?
    private var environment: ORTEnv?
    private var importedFile: URL? {
        let root = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("GHOSTLINE-RVC-ONNX", isDirectory: true)
        return root.appendingPathComponent("imported-model.onnx")
    }

    func importAndValidate(_ source: URL) {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        graphLoaded = false
        session = nil
        environment = nil
        guard source.pathExtension.lowercased() == "onnx", let destination = importedFile else {
            status = "Choose a .onnx model file, not a PyTorch .pth checkpoint."
            return
        }
        let accessed = source.startAccessingSecurityScopedResource()
        defer { if accessed { source.stopAccessingSecurityScopedResource() } }
        do {
            let metadata = try FileManager.default.attributesOfItem(atPath: source.path)
            let size = (metadata[.size] as? NSNumber)?.uint64Value ?? 0
            guard size >= 128, size < 1_000_000_000 else {
                status = "ONNX file size must be between 128 bytes and 1 GB."
                return
            }
            try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            let staged = destination.deletingLastPathComponent()
                .appendingPathComponent(UUID().uuidString + ".onnx")
            try FileManager.default.copyItem(at: source, to: staged)
            defer { try? FileManager.default.removeItem(at: staged) }
            let env = try ORTEnv(loggingLevel: .warning)
            let graph = try ORTSession(env: env, modelPath: staged.path, sessionOptions: nil)
            let inputs = try graph.inputNames()
            let outputs = try graph.outputNames()
            guard !inputs.isEmpty, !outputs.isEmpty else {
                status = "Model loaded but lacks required input/output tensors."
                return
            }
            let hash = try hashFile(staged)
            // Only replace previous model when ONNX Runtime can load the new graph.
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.copyItem(at: staged, to: destination)
            environment = env
            session = try ORTSession(env: env, modelPath: destination.path, sessionOptions: nil)
            graphInputs = inputs
            graphOutputs = outputs
            sha256 = hash
            modelName = source.lastPathComponent
            graphLoaded = true
            status = "ONNX Runtime loaded the model on this iPhone. No audio was synthesized. RVC prerequisites and tensor feeds remain unverified."
        } catch {
            status = "ONNX Runtime graph load failed: \(error.localizedDescription)"
        }
    }

    private func hashFile(_ file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { try? handle.close() }
        var digest = SHA256()
        while let chunk = try handle.read(upToCount: 1024 * 1024), !chunk.isEmpty {
            digest.update(data: chunk)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }
}

struct RVCOnnxRuntimeView: View {
    @StateObject private var lab = RVCOnnxRuntimeLab()
    @State private var showImporter = false
    var body: some View {
        Form {
            Section("ONNX Runtime • iPhone compatibility") {
                Text("This tests the model-execution engine with a locally imported ONNX graph. RVC .pth checkpoints require conversion into ONNX first.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button("Import and load .onnx model") { showImporter = true }
                    .disabled(lab.busy)
                Label(lab.graphLoaded ? "Model loaded into ONNX Runtime" : "No ONNX graph loaded",
                      systemImage: lab.graphLoaded ? "checkmark.circle" : "circle.dotted")
                Text(lab.status).font(.footnote)
            }
            if lab.graphLoaded {
                Section("Graph metadata • not speech verification") {
                    if let name = lab.modelName { Text(name) }
                    if let hash = lab.sha256 { Text("SHA-256: " + hash).font(.caption2).monospaced() }
                    Text("Inputs: " + lab.graphInputs.joined(separator: ", "))
                    Text("Outputs: " + lab.graphOutputs.joined(separator: ", "))
                }
            }
            Section("Required for real RVC conversion") {
                Text("1. Verified source model conversion from PyTorch checkpoints.")
                Text("2. Compatible content encoder and pitch extractor.")
                Text("3. Tensor preparation, RVC synthesis, and waveform post-processing.")
                Text("4. Offline iPhone playback and listening verification.")
                Text("Model loading alone never counts as a functioning voice.")
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("RVC ONNX Runtime")
        .fileImporter(isPresented: $showImporter, allowedContentTypes: [.data]) { result in
            if case .success(let url) = result { lab.importAndValidate(url) }
            if case .failure(let error) = result {
                lab.status = "Import cancelled or failed: \(error.localizedDescription)"
            }
        }
    }
}
