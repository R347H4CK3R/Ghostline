import Foundation
import CoreML

struct ConversionProfile: Codable {
    let id, ttsEmbeddingSHA256, converterRevision, referenceAudioSHA256: String
    let embedding: [Float]
}
struct ConversionPack {
    struct Manifest: Decodable { let engine, sourceRevision: String; let files: [AssetRecord] }
    let root: URL
    let manifest: Manifest
    static func read() throws -> ConversionPack {
        guard let root = Bundle.main.url(forResource: "OpenVoice", withExtension: nil) else { throw ConversionError.missingAssets }
        let manifest = try JSONDecoder().decode(Manifest.self, from: Data(contentsOf: root.appendingPathComponent("model-manifest.json")))
        guard manifest.engine == "OpenVoiceV2", !manifest.files.isEmpty else { throw ConversionError.damagedAssets }
        try Catalog.validateAssets(root: root, files: manifest.files)
        return ConversionPack(root: root, manifest: manifest)
    }
    func profile(for voice: VoiceProfile) throws -> ConversionProfile {
        guard !voice.id.contains("/"), !voice.id.contains("..") else { throw ConversionError.invalidProfile }
        let url = root.appendingPathComponent("Profiles").appendingPathComponent(voice.id).appendingPathExtension("json")
        let result = try JSONDecoder().decode(ConversionProfile.self, from: Data(contentsOf: url))
        guard result.id == voice.id, result.ttsEmbeddingSHA256 == voice.sha256, result.converterRevision == manifest.sourceRevision,
              result.embedding.count == 256, result.embedding.allSatisfy(\.isFinite), result.embedding.reduce(0, { $0 + $1 * $1 }) > 1e-8 else { throw ConversionError.invalidProfile }
        return result
    }
}
struct ConversionResult {
    let sourceSeconds, outputSeconds: Double
    let sourceEmbedding: [Float]
}
actor OfflineVoiceConverter {
    private let computeUnits: MLComputeUnits
    private var pack: ConversionPack?
    private var encoder: MLModel?
    private var converter: MLModel?
    init(computeUnits: MLComputeUnits = .cpuAndGPU) { self.computeUnits = computeUnits }
    private func assets() throws -> ConversionPack {
        if let pack { return pack }
        let loaded = try ConversionPack.read(); pack = loaded; return loaded
    }
    private func model(named name: String, pack: ConversionPack) throws -> MLModel {
        let configuration = MLModelConfiguration(); configuration.computeUnits = computeUnits
        return try MLModel(contentsOf: pack.root.appendingPathComponent(name).appendingPathExtension("mlmodelc"), configuration: configuration)
    }
    private func array(_ values: [Float], shape: [Int]) throws -> MLMultiArray {
        let result = try MLMultiArray(shape: shape.map { NSNumber(value: $0) }, dataType: .float16)
        guard result.count == values.count, values.allSatisfy(\.isFinite) else { throw ConversionError.modelFailure }
        let pointer = result.dataPointer.bindMemory(to: Float16.self, capacity: values.count)
        for i in values.indices { pointer[i] = Float16(values[i]) }
        return result
    }
    private func embed(_ spectrum: LinearSpectrum) throws -> [Float] {
        let pack = try assets()
        converter = nil
        if encoder == nil { encoder = try model(named: "OpenVoice_SpeakerEncoder", pack: pack) }
        guard let encoder else { throw ConversionError.modelFailure }
        let input = try array(spectrum.values, shape: [1, spectrum.frames, 513])
        let output = try encoder.prediction(from: MLDictionaryFeatureProvider(dictionary: ["spectrogram": input]))
        guard let tensor = output.featureValue(for: "speaker_embedding")?.multiArrayValue,
              tensor.shape.map(\.intValue) == [1, 256, 1] else { throw ConversionError.modelFailure }
        let values = (0..<256).map { tensor[[0, NSNumber(value: $0), 0]].floatValue }
        guard values.allSatisfy(\.isFinite), values.reduce(0, { $0 + $1 * $1 }) > 1e-8 else { throw ConversionError.modelFailure }
        return values
    }
    func extractEmbedding(from url: URL) throws -> [Float] {
        try Task.checkCancellation()
        return try embed(ConversionAudio.spectrum(ConversionAudio.readMono(url)))
    }
    func targetProfile(for voice: VoiceProfile) throws -> ConversionProfile { try assets().profile(for: voice) }
    func sourceRevision() throws -> String { try assets().manifest.sourceRevision }
    func convert(source: URL, target: [Float], destination: URL, progress: @escaping @Sendable (String) -> Void = { _ in }) throws -> ConversionResult {
        guard target.count == 256, target.allSatisfy(\.isFinite) else { throw ConversionError.invalidProfile }
        try Task.checkCancellation()
        progress("Reading your recording")
        let samples = try ConversionAudio.readMono(source)
        let spectrum = try ConversionAudio.spectrum(samples)
        progress("Preparing your voice")
        let sourceSpeaker = try embed(spectrum)
        encoder = nil // Copy the small embedding, then release the encoder before converter loading.
        try Task.checkCancellation()
        let pack = try assets()
        progress("Starting voice changing")
        if converter == nil { converter = try model(named: "OpenVoice_VoiceConverter", pack: pack) }
        guard let converter else { throw ConversionError.modelFailure }
        let features = try MLDictionaryFeatureProvider(dictionary: [
            "spectrogram": array(spectrum.frequencyMajor, shape: [1, 513, spectrum.frames]),
            "spec_lengths": array([Float(spectrum.frames)], shape: [1]),
            "source_speaker": array(sourceSpeaker, shape: [1, 256, 1]),
            "target_speaker": array(target, shape: [1, 256, 1])
        ])
        progress("Changing your voice")
        let prediction = try converter.prediction(from: features)
        try Task.checkCancellation()
        guard let audio = prediction.featureValue(for: "audio")?.multiArrayValue,
              audio.shape.count == 3, audio.shape[0].intValue == 1, audio.shape[1].intValue == 1,
              audio.shape[2].intValue >= 2205, audio.shape[2].intValue <= 221000 else { throw ConversionError.modelFailure }
        let count = audio.shape[2].intValue; let stride = audio.strides[2].intValue
        var output = [Float](repeating: 0, count: count)
        switch audio.dataType {
        case .float16:
            let pointer = audio.dataPointer.assumingMemoryBound(to: Float16.self)
            for i in 0..<count { output[i] = Float(pointer[i * stride]) }
        case .float32:
            let pointer = audio.dataPointer.assumingMemoryBound(to: Float.self)
            for i in 0..<count { output[i] = pointer[i * stride] }
        default: throw ConversionError.modelFailure
        }
        guard abs(Double(output.count - samples.count) / ConversionAudio.sampleRate) < 0.04 else { throw ConversionError.modelFailure }
        progress("Saving your changed voice")
        do { try ConversionAudio.write(output, to: destination) }
        catch { try? FileManager.default.removeItem(at: destination); throw error }
        return ConversionResult(sourceSeconds: Double(samples.count) / ConversionAudio.sampleRate, outputSeconds: Double(count) / ConversionAudio.sampleRate, sourceEmbedding: sourceSpeaker)
    }
    func unload() { encoder = nil; converter = nil; pack = nil }
    static func cosine(_ a: [Float], _ b: [Float]) -> Double {
        guard a.count == b.count else { return 0 }
        var dot = 0.0, aa = 0.0, bb = 0.0
        for i in a.indices { dot += Double(a[i]) * Double(b[i]); aa += Double(a[i]) * Double(a[i]); bb += Double(b[i]) * Double(b[i]) }
        return dot / max(1e-12, sqrt(aa * bb))
    }
}
