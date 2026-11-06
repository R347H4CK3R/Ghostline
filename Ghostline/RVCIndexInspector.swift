import Foundation

// A bounded FAISS header probe, not a FAISS decoder and NOT evidence that
// RVC index retrieval is implemented. Never load the full index into RAM here.
enum GhostlineRVCIndexInspector {
    struct Header {
        let family: String
        let dimension: Int
        let vectorCount: Int64
        let trained: Bool
        let metric: Int
        var likelyRVCDimension: Bool { dimension == 256 || dimension == 768 }
    }

    enum Failure: Error, LocalizedError {
        case truncated, unknownType, invalidDimension, invalidCount, invalidTrainingFlag, invalidMetric
        var errorDescription: String? {
            switch self {
            case .truncated: return "Not a complete FAISS index header"
            case .unknownType: return "Unrecognized FAISS index family; cannot safely classify this .index"
            case .invalidDimension: return "Invalid FAISS vector dimension"
            case .invalidCount: return "FAISS index contains no usable vectors or has an invalid count"
            case .invalidTrainingFlag: return "Invalid FAISS training flag"
            case .invalidMetric: return "Invalid or incomplete FAISS distance metric"
            }
        }
    }

    private static let families: Set<String> = [
        "IwFl", "IwPQ", "IwSq", "IwFd", "IxF2", "IxFI", "IxFl",
        "IxMp", "IxM2", "IxPT", "IxPq", "IxSQ", "IxRF", "IHNf"
    ]

    private static func unsignedLE(_ data: Data, from offset: Int, count: Int) -> UInt64 {
        (0..<count).reduce(UInt64(0)) { result, i in
            result | (UInt64(data[offset + i]) << (8 * i))
        }
    }

    static func inspectHeader(_ data: Data) throws -> Header {
        guard data.count >= 37 else { throw Failure.truncated }
        let family = String(data: data.prefix(4), encoding: .ascii) ?? ""
        guard families.contains(family) else { throw Failure.unknownType }
        let dimension = Int(unsignedLE(data, from: 4, count: 4))
        guard (1...8192).contains(dimension) else { throw Failure.invalidDimension }
        let count = Int64(bitPattern: unsignedLE(data, from: 8, count: 8))
        guard count > 0 else { throw Failure.invalidCount }
        let flag = data[32]
        guard flag == 0 || flag == 1 else { throw Failure.invalidTrainingFlag }
        let metric = Int(unsignedLE(data, from: 33, count: 4))
        guard (0...30).contains(metric),
              metric <= 1 || data.count >= 41 else { throw Failure.invalidMetric }
        return Header(family: family, dimension: dimension, vectorCount: count,
                      trained: flag == 1, metric: metric)
    }

    static func inspect(_ url: URL) throws -> Header {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: 41) ?? Data()
        return try inspectHeader(data)
    }
}
