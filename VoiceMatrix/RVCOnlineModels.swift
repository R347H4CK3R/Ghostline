import Foundation

/// RVC metadata is deliberately separate from F5 references and their private cache.
/// This protocol offers laptop conversion only, never offline RVC or text synthesis.
enum RVCOnlineError: Error, LocalizedError, Equatable, Sendable {
    case invalidCatalog, invalidRequest, invalidResponse, invalidAudio, invalidConnection
    case unavailable, authenticationRequired, modelChanged, busy, noRequest
    case httpStatus(Int)
    /// Do not render arbitrary transport/file error descriptions containing paths,
    /// URLs or credentials. Only this fixed domain error vocabulary is displayed.
    static func message(for error: Error) -> String {
        if let known = error as? Self, let text = known.errorDescription { return text }
        return "The laptop connection could not be verified. Check pairing and try again."
    }
    var errorDescription: String? {
        switch self {
        case .invalidCatalog: return "The laptop RVC catalog is invalid or unsupported. Refresh it before choosing a voice."
        case .invalidRequest: return "This RVC request is invalid. Choose a current model and a mono PCM16 WAV between 0.2 and 30 seconds."
        case .invalidResponse: return "The laptop response did not match this RVC request. No audio was accepted."
        case .invalidAudio: return "The RVC audio failed its size, format or integrity checks."
        case .invalidConnection: return "Connect to the laptop using its HTTPS connection first."
        case .unavailable: return "Online RVC conversion is unavailable. RVC offline conversion and text synthesis are not supported."
        case .authenticationRequired: return "The laptop rejected this connection. Check Tailscale or import the current pairing file."
        case .modelChanged: return "The laptop model changed. Refresh the RVC catalog and choose it again."
        case .busy: return "Finish or cancel the current RVC request before starting another."
        case .noRequest: return "There is no RVC request to check."
        case .httpStatus: return "The laptop could not complete this RVC request. Reconnect and check its status before submitting again."
        }
    }
}

enum RVCOnlineValidation {
    static func hash(_ value: String) -> Bool {
        value.utf8.count == 64 && value.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
    static func id(_ value: String) -> Bool {
        (1...100).contains(value.utf8.count) && value.utf8.allSatisfy {
            (97...122).contains($0) || (48...57).contains($0) || $0 == 45 || $0 == 95
        }
    }
    static func uuid(_ value: String) -> Bool { UUID(uuidString: value)?.uuidString.lowercased() == value }
    static func label(_ value: String, limit: Int) -> Bool {
        (1...limit).contains(value.unicodeScalars.count) &&
        !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        !value.unicodeScalars.contains { CharacterSet.controlCharacters.contains($0) }
    }
}

struct RVCOnlineModel: Codable, Sendable, Equatable, Identifiable {
    let id, name: String
    let categories: [String]
    let modelSHA256, indexSHA256, revision: String
    let identityVerified, likenessVerified: Bool
    func validate() throws {
        guard RVCOnlineValidation.id(id), RVCOnlineValidation.label(name, limit: 200),
              (1...20).contains(categories.count), Set(categories).count == categories.count,
              categories.allSatisfy({ RVCOnlineValidation.label($0, limit: 100) }),
              [modelSHA256, indexSHA256, revision].allSatisfy(RVCOnlineValidation.hash),
              !identityVerified, !likenessVerified else { throw RVCOnlineError.invalidCatalog }
    }
}

struct RVCOnlineCatalog: Decodable, Sendable {
    static let byteLimit = 1_048_576
    let schemaVersion: Int
    let format: String
    let onlineConversionAvailable, offlineAvailable, textToSpeechAvailable: Bool
    let models: [RVCOnlineModel]
    static func decode(_ data: Data) throws -> Self {
        guard data.count <= byteLimit else { throw RVCOnlineError.invalidCatalog }
        let catalog: Self
        do { catalog = try JSONDecoder().decode(Self.self, from: data) }
        catch { throw RVCOnlineError.invalidCatalog }
        guard catalog.schemaVersion == 1, catalog.format == "rvc-online-conversion-v1",
              !catalog.offlineAvailable, !catalog.textToSpeechAvailable,
              catalog.models.count <= 64, Set(catalog.models.map(\.id)).count == catalog.models.count else {
            throw RVCOnlineError.invalidCatalog
        }
        try catalog.models.forEach { try $0.validate() }
        return catalog
    }
}

/// Immutable retry identity. The production connection hashes the actual bytes
/// when constructing this request and checks them again before any transmission.
struct RVCOnlineRequest: Encodable, Sendable, Equatable {
    static let bodyByteLimit = 4 * 1024 * 1024 + 4096
    let schemaVersion = 1
    let requestID, modelID, modelSHA256, indexSHA256, revision, inputSHA256, wavBase64: String
    init(model: RVCOnlineModel, wav: Data, inputSHA256: String, id: UUID = UUID()) throws {
        try model.validate()
        _ = try RVCOnlineWAV.inspect(wav)
        guard RVCOnlineValidation.hash(inputSHA256) else { throw RVCOnlineError.invalidRequest }
        requestID = id.uuidString.lowercased(); modelID = model.id
        modelSHA256 = model.modelSHA256; indexSHA256 = model.indexSHA256; revision = model.revision
        self.inputSHA256 = inputSHA256; wavBase64 = wav.base64EncodedString()
    }
    func encodedBody() throws -> Data {
        let encoder = JSONEncoder()
        // Escaping every slash can make otherwise valid base64 exceed the
        // server's 4 MiB + 4096-byte JSON bound.
        encoder.outputFormatting = [.withoutEscapingSlashes]
        let body = try encoder.encode(self)
        guard body.count <= Self.bodyByteLimit else { throw RVCOnlineError.invalidRequest }
        return body
    }
}

enum RVCOnlineStatus: String, Decodable, Sendable {
    case queued, running, waitingForResources = "waiting-for-resources", cancelling, cancelled, failed, succeeded
    var terminal: Bool { self == .cancelled || self == .failed || self == .succeeded }
}

struct RVCOnlineSnapshot: Decodable, Sendable, Equatable {
    struct Result: Decodable, Sendable, Equatable {
        let sha256: String
        let bytes, sampleRate: Int
        let seconds: Double
        func validate() throws {
            guard RVCOnlineValidation.hash(sha256), (44...RVCOnlineWAV.byteLimit).contains(bytes),
                  sampleRate == 40000, seconds.isFinite, (0.2...30).contains(seconds),
                  Double(bytes) >= seconds * Double(sampleRate) * 2 else { throw RVCOnlineError.invalidResponse }
        }
    }
    static let byteLimit = 65_536
    let schemaVersion: Int
    let requestID, modelID, modelSHA256, indexSHA256, revision, inputSHA256: String
    let status: RVCOnlineStatus
    let createdAt, updatedAt: Double
    let result: Result?
    static func decode(_ data: Data, for request: RVCOnlineRequest) throws -> Self {
        guard data.count <= byteLimit else { throw RVCOnlineError.invalidResponse }
        let value: Self
        do { value = try JSONDecoder().decode(Self.self, from: data) }
        catch { throw RVCOnlineError.invalidResponse }
        try value.validate(for: request)
        return value
    }
    func validate(for request: RVCOnlineRequest) throws {
        guard schemaVersion == 1, createdAt.isFinite, updatedAt.isFinite, createdAt >= 0, updatedAt >= 0,
              RVCOnlineValidation.uuid(requestID), requestID == request.requestID,
              modelID == request.modelID, modelSHA256 == request.modelSHA256,
              indexSHA256 == request.indexSHA256, revision == request.revision,
              inputSHA256 == request.inputSHA256 else { throw RVCOnlineError.invalidResponse }
        if status == .succeeded {
            guard let result else { throw RVCOnlineError.invalidResponse }; try result.validate()
        } else if result != nil { throw RVCOnlineError.invalidResponse }
    }
}

struct RVCOnlineEndpoint: Sendable {
    let root: URL
    init(root: URL) throws {
        guard root.scheme == "https", let host = root.host, !host.isEmpty,
              root.user == nil, root.password == nil, root.query == nil, root.fragment == nil,
              root.path.isEmpty || root.path == "/" else { throw RVCOnlineError.invalidConnection }
        self.root = root
    }
    var catalog: URL { root.appendingPathComponent("rvc/models") }
    var conversions: URL { root.appendingPathComponent("rvc/conversions") }
    func job(_ requestID: String) throws -> URL {
        guard RVCOnlineValidation.uuid(requestID) else { throw RVCOnlineError.invalidRequest }
        return conversions.appendingPathComponent(requestID)
    }
}

/// Bounded RIFF parsing without unaligned loads, integer overflow or AVFoundation.
/// Extra chunks are allowed, but duplicate format/audio chunks and trailing bytes
/// are rejected. No conversion or resampling is hidden in the transport.
struct RVCOnlineWAV: Sendable {
    static let byteLimit = 3 * 1024 * 1024
    let sampleRate, frames: Int
    var seconds: Double { Double(frames) / Double(sampleRate) }
    static func inspect(_ raw: Data) throws -> Self {
        guard (44...byteLimit).contains(raw.count) else { throw RVCOnlineError.invalidAudio }
        let data = [UInt8](raw)
        func uint(_ offset: Int, _ size: Int) -> Int {
            var number = 0
            for i in 0..<size { number |= Int(data[offset + i]) << (i * 8) }; return number
        }
        func tag(_ offset: Int, _ text: String) -> Bool { Array(data[offset..<(offset + 4)]) == Array(text.utf8) }
        guard tag(0, "RIFF"), tag(8, "WAVE"), uint(4, 4) == data.count - 8 else { throw RVCOnlineError.invalidAudio }
        var offset = 12, sampleRate: Int?, audioBytes: Int?, audioStart: Int?
        while offset < data.count {
            guard data.count - offset >= 8 else { throw RVCOnlineError.invalidAudio }
            let size = uint(offset + 4, 4), start = offset + 8
            guard size <= data.count - start else { throw RVCOnlineError.invalidAudio }
            if tag(offset, "fmt ") {
                guard sampleRate == nil, size >= 16, uint(start, 2) == 1, uint(start + 2, 2) == 1,
                      uint(start + 14, 2) == 16, uint(start + 12, 2) == 2 else { throw RVCOnlineError.invalidAudio }
                let rate = uint(start + 4, 4)
                guard [16000, 22050, 24000, 32000, 40000, 44100, 48000].contains(rate), uint(start + 8, 4) == rate * 2 else { throw RVCOnlineError.invalidAudio }
                sampleRate = rate
            } else if tag(offset, "data") {
                guard sampleRate != nil, audioBytes == nil, size > 0, size % 2 == 0 else { throw RVCOnlineError.invalidAudio }
                audioBytes = size; audioStart = start
            }
            let padding = size % 2
            guard padding <= data.count - start - size else { throw RVCOnlineError.invalidAudio }
            offset = start + size + padding
        }
        guard let rate = sampleRate, let count = audioBytes, let start = audioStart else { throw RVCOnlineError.invalidAudio }
        let value = Self(sampleRate: rate, frames: count / 2)
        guard (0.2...30).contains(value.seconds) else { throw RVCOnlineError.invalidAudio }
        // Match the laptop's signal sanity gate. This is not a speech-quality,
        // identity or likeness measurement.
        var squares: Int64 = 0
        for index in stride(from: start, to: start + count, by: 2) {
            let rawSample = uint(index, 2)
            let sample = rawSample >= 32768 ? rawSample - 65536 : rawSample
            guard abs(sample) < 32767 else { throw RVCOnlineError.invalidAudio }
            squares += Int64(sample) * Int64(sample)
        }
        let rms = sqrt(Double(squares) / Double(value.frames)) / 32768
        guard rms > 0.0001 else { throw RVCOnlineError.invalidAudio }
        return value
    }
}
