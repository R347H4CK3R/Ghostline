import Foundation
import CoreML
import CryptoKit

struct ConversionProfile: Codable {
    let id, ttsEmbeddingSHA256, converterRevision, referenceAudioSHA256: String
    let embedding: [Float]
    private enum CodingKeys: String, CodingKey { case id, ttsEmbeddingSHA256, converterRevision, referenceAudioSHA256, embedding, embeddingFP16Base64 }
    init(id: String, ttsEmbeddingSHA256: String, converterRevision: String, referenceAudioSHA256: String, embedding: [Float]) {
        self.id = id; self.ttsEmbeddingSHA256 = ttsEmbeddingSHA256; self.converterRevision = converterRevision
        self.referenceAudioSHA256 = referenceAudioSHA256; self.embedding = embedding
    }
    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        ttsEmbeddingSHA256 = try values.decode(String.self, forKey: .ttsEmbeddingSHA256)
        converterRevision = try values.decode(String.self, forKey: .converterRevision)
        referenceAudioSHA256 = try values.decode(String.self, forKey: .referenceAudioSHA256)
        if let full = try values.decodeIfPresent([Float].self, forKey: .embedding) { embedding = full }
        else {
            let encoded = try values.decode(String.self, forKey: .embeddingFP16Base64)
            guard let data = Data(base64Encoded: encoded), data.count == 512 else { throw ConversionError.invalidProfile }
            embedding = stride(from: 0, to: 512, by: 2).map { index in
                Float(Float16(bitPattern: UInt16(data[index]) | UInt16(data[index + 1]) << 8))
            }
        }
        guard embedding.count == 256, embedding.allSatisfy(\.isFinite) else { throw ConversionError.invalidProfile }
    }
    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(id, forKey: .id); try values.encode(ttsEmbeddingSHA256, forKey: .ttsEmbeddingSHA256)
        try values.encode(converterRevision, forKey: .converterRevision); try values.encode(referenceAudioSHA256, forKey: .referenceAudioSHA256)
        var data = Data(); data.reserveCapacity(512)
        for value in embedding {
            let bits = Float16(value).bitPattern
            data.append(UInt8(truncatingIfNeeded: bits)); data.append(UInt8(truncatingIfNeeded: bits >> 8))
        }
        try values.encode(data.base64EncodedString(), forKey: .embeddingFP16Base64)
    }
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
    func profile(for voice: VoiceProfile, phononRoot: URL, manifest: VoiceManifest) throws -> ConversionProfile {
        guard !voice.id.contains("/"), !voice.id.contains("..") else { throw ConversionError.invalidProfile }
        let base: VoiceProfile
        let url: URL
        if voice.engine == "phonon31m-openvoicev2" {
            guard let sourceID = voice.baseVoiceID, let source = manifest.voices.first(where: { $0.id == sourceID && $0.engine == "phonon31m" }),
                  !voice.path.hasPrefix("/"), !voice.path.split(separator: "/").contains("..") else { throw ConversionError.invalidProfile }
            base = source; url = phononRoot.appendingPathComponent(voice.path)
        } else {
            base = voice; url = root.appendingPathComponent("Profiles").appendingPathComponent(voice.id).appendingPathExtension("json")
        }
        let result = try JSONDecoder().decode(ConversionProfile.self, from: Data(contentsOf: url))
        guard result.id == voice.id, result.ttsEmbeddingSHA256 == base.sha256, result.converterRevision == self.manifest.sourceRevision,
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
    private var cachedSource: (hash: String, samples: [Float], spectrum: LinearSpectrum, embedding: [Float])?
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
        return try embed(ConversionAudio.spectrum(ConversionAudio.readMono(url, minimumSeconds: 0.5, isReference: true)))
    }
    func targetProfile(for voice: VoiceProfile, root: URL, manifest: VoiceManifest) throws -> ConversionProfile { try assets().profile(for: voice, phononRoot: root, manifest: manifest) }
    func sourceRevision() throws -> String { try assets().manifest.sourceRevision }
    func convert(source: URL, target: [Float], destination: URL, progress: @escaping @Sendable (String) -> Void = { _ in }) throws -> ConversionResult {
        guard target.count == 256, target.allSatisfy(\.isFinite) else { throw ConversionError.invalidProfile }
        try Task.checkCancellation()
        progress("Reading your recording")
        let handle = try FileHandle(forReadingFrom: source)
        var sourceHasher = SHA256()
        do {
            while let data = try handle.read(upToCount: 1_048_576), !data.isEmpty { sourceHasher.update(data: data) }
            try handle.close()
        } catch { try? handle.close(); throw error }
        let sourceHash = sourceHasher.finalize().map { String(format: "%02x", $0) }.joined()
        let samples: [Float]
        let spectrum: LinearSpectrum
        let sourceSpeaker: [Float]
        progress("Preparing your voice")
        if let cachedSource, cachedSource.hash == sourceHash {
            samples = cachedSource.samples; spectrum = cachedSource.spectrum; sourceSpeaker = cachedSource.embedding
        } else {
            samples = try ConversionAudio.readMono(source, minimumSeconds: 0.15)
            spectrum = try ConversionAudio.spectrum(samples)
            sourceSpeaker = try embed(spectrum)
            cachedSource = (sourceHash, samples, spectrum, sourceSpeaker)
        }
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
    func releaseModels() { encoder = nil; converter = nil; cachedSource = nil }
    func unload() { releaseModels(); pack = nil }
    static func cosine(_ a: [Float], _ b: [Float]) -> Double {
        guard a.count == b.count else { return 0 }
        var dot = 0.0, aa = 0.0, bb = 0.0
        for i in a.indices { dot += Double(a[i]) * Double(b[i]); aa += Double(a[i]) * Double(a[i]); bb += Double(b[i]) * Double(b[i]) }
        return dot / max(1e-12, sqrt(aa * bb))
    }
}
