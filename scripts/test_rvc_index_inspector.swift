import Foundation

@main
struct RVCIndexInspectorTests {
    static func le(_ value: UInt64, count: Int) -> Data {
        Data((0..<count).map { UInt8(truncatingIfNeeded: value >> (8 * $0)) })
    }
    static func fixture(family: String = "IwFl", dimension: Int = 768,
                        vectors: Int64 = 100, trained: UInt8 = 1,
                        metric: Int = 1) -> Data {
        var data = Data(family.utf8)
        data.append(le(UInt64(dimension), count: 4))
        data.append(le(UInt64(bitPattern: vectors), count: 8))
        data.append(le(1 << 20, count: 8))
        data.append(le(1 << 20, count: 8))
        data.append(trained)
        data.append(le(UInt64(metric), count: 4))
        if metric > 1 { data.append(le(0, count: 4)) }
        return data + Data(repeating: 0, count: 1024)
    }
    static func reject(_ data: Data, label: String) {
        do {
            _ = try GhostlineRVCIndexInspector.inspectHeader(data)
            fatalError("Accepted invalid FAISS header: " + label)
        } catch is GhostlineRVCIndexInspector.Failure {
            print("PASS rejected " + label)
        } catch {
            fatalError("Unexpected failure: " + String(describing: error))
        }
    }
    static func main() throws {
        for family in ["IwFl", "IxF2", "IxFI", "IxMp", "IxPT"] {
            let header = try GhostlineRVCIndexInspector.inspectHeader(fixture(family: family))
            precondition(header.family == family && header.dimension == 768)
            precondition(header.vectorCount == 100 && header.trained && header.metric == 1)
            precondition(header.likelyRVCDimension)
        }
        let header = try GhostlineRVCIndexInspector.inspectHeader(fixture(dimension: 256, trained: 0, metric: 0))
        precondition(!header.trained && header.likelyRVCDimension)
        let nonstandard = try GhostlineRVCIndexInspector.inspectHeader(fixture(dimension: 1024))
        precondition(!nonstandard.likelyRVCDimension)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".index")
        defer { try? FileManager.default.removeItem(at: url) }
        try fixture().write(to: url)
        let local = try GhostlineRVCIndexInspector.inspect(url)
        precondition(local.family == "IwFl" && local.dimension == 768)
        reject(Data(repeating: 0, count: 18), label: "truncated")
        reject(fixture(family: "RIFF"), label: "renamed WAV")
        reject(fixture(family: "PICK"), label: "renamed pickle")
        reject(fixture(dimension: 0), label: "zero-dimensional")
        reject(fixture(dimension: 9000), label: "implausible dimension")
        reject(fixture(vectors: 0), label: "empty vector table")
        reject(fixture(vectors: -1), label: "negative vector count")
        reject(fixture(trained: 3), label: "invalid trained flag")
        reject(fixture(metric: 31), label: "invalid metric")
        reject(Data(fixture(metric: 2).prefix(37)), label: "truncated metric arg")
        print("FAISS header probes passed; no full index decode or iPhone retrieval inference claimed.")
    }
}
