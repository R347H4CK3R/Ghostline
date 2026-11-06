import SwiftUI
import UniformTypeIdentifiers
import CoreML
import CryptoKit

/// A safe local compatibility probe for an already-converted Core ML voice graph.
/// Loading a graph is not voice conversion and does not certify a speaker identity.
@MainActor
final class RVCCoreMLModelLab: ObservableObject {
    @Published var status = "Import a converted Core ML .mlmodel package for local compatibility testing."
    @Published var modelName: String?
    @Published var graphInputs: [String] = []
    @Published var graphOutputs: [String] = []
    @Published var busy = false
    @Published var graphLoaded = false
    private var compiledModel: MLModel?

    func importAndValidate(_ source: URL) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        compiledModel = nil
        graphLoaded = false
        graphInputs = []
        graphOutputs = []
        modelName = nil
        guard source.pathExtension.lowercased() == "mlmodel" else {
            status = "Choose a converted .mlmodel file. Native RVC .pth is not directly executable."
            return
        }
        let accessed = source.startAccessingSecurityScopedResource()
        defer { if accessed { source.stopAccessingSecurityScopedResource() } }
        do {
            let attrs = try FileManager.default.attributesOfItem(atPath: source.path)
            let bytes = (attrs[.size] as? NSNumber)?.uint64Value ?? 0
            guard bytes >= 128 && bytes <= 900_000_000 else {
                status = "Invalid model size (128 bytes to 900 MB required)."
                return
            }
            let folder = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("GHOSTLINE-RVC-CoreML", isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let staged = folder.appendingPathComponent(UUID().uuidString + ".mlmodel")
            try FileManager.default.copyItem(at: source, to: staged)
            defer { try? FileManager.default.removeItem(at: staged) }
            let compiled = try await MLModel.compileModel(at: staged)
            let config = MLModelConfiguration()
            config.computeUnits = .cpuAndNeuralEngine
            let model = try MLModel(contentsOf: compiled, configuration: config)
            let inputNames = model.modelDescription.inputDescriptionsByName.keys.sorted()
            let outputNames = model.modelDescription.outputDescriptionsByName.keys.sorted()
            guard !inputNames.isEmpty && !outputNames.isEmpty else {
                status = "Model loaded without usable input/output tensors."
                return
            }
            self.compiledModel = model
            self.modelName = source.lastPathComponent
            self.graphInputs = inputNames
            self.graphOutputs = outputNames
            self.graphLoaded = true
            status = "Converted Core ML graph loaded locally. No voice audio has been synthesized or verified."
        } catch {
            status = "Core ML graph load failed: \(error.localizedDescription)"
        }
    }
}

struct RVCCoreMLModelView: View {
    @StateObject private var lab = RVCCoreMLModelLab()
    @State private var showImporter = false
    var body: some View {
        Form {
            Section("Core ML • iPhone model compatibility") {
                Text("Load an already-converted Core ML voice model locally without downloading an additional runtime. PyTorch .pth and ONNX graphs require a separately validated conversion process.")
                    .font(.footnote).foregroundStyle(.secondary)
                Button("Import converted .mlmodel") { showImporter = true }
                    .disabled(lab.busy)
                Label(lab.graphLoaded ? "Core ML graph loaded" : "No converted model loaded",
                      systemImage: lab.graphLoaded ? "checkmark.circle" : "circle.dotted")
                Text(lab.status).font(.footnote)
            }
            if lab.graphLoaded {
                Section("Model interface") {
                    if let name = lab.modelName { Text(name) }
                    Text("Inputs: " + lab.graphInputs.joined(separator: ", "))
                    Text("Outputs: " + lab.graphOutputs.joined(separator: ", "))
                    Text("A loaded graph is not proof of RVC conversion, functional speech or identity accuracy.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section("Remaining conversion work") {
                Text("1. Convert a legally usable RVC checkpoint to a compatible neural graph.")
                Text("2. Implement matching content encoder and pitch extraction.")
                Text("3. Build input tensors, synthesize output samples, and export valid WAV.")
                Text("4. Verify airplane-mode output on the physical target iPhone.")
            }
        }
        .navigationTitle("RVC Core ML Test")
        .fileImporter(isPresented: $showImporter, allowedContentTypes: [.data]) { result in
            switch result {
            case .success(let url): Task { await lab.importAndValidate(url) }
            case .failure(let error): lab.status = "Import failed: \(error.localizedDescription)"
            }
        }
    }
}
