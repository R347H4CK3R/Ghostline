import Foundation

@main
struct GhostlineWAVInspectorTests {
    static func append16(_ value: Int, to data: inout Data) {
        data.append(UInt8(value & 255))
        data.append(UInt8((value >> 8) & 255))
    }
    static func append32(_ value: Int, to data: inout Data) {
        append16(value & 65535, to: &data)
        append16((value >> 16) & 65535, to: &data)
    }
    static func wav(_ samples: [Int16]) -> Data {
        var bytes = Data("RIFF".utf8)
        append32(36 + samples.count * 2, to: &bytes)
        bytes.append(Data("WAVEfmt ".utf8))
        append32(16, to: &bytes)
        append16(1, to: &bytes) // PCM
        append16(1, to: &bytes) // mono
        append32(16_000, to: &bytes)
        append32(32_000, to: &bytes)
        append16(2, to: &bytes)
        append16(16, to: &bytes)
        bytes.append(Data("data".utf8))
        append32(samples.count * 2, to: &bytes)
        for sample in samples {
            append16(Int(UInt16(bitPattern: sample)), to: &bytes)
        }
        return bytes
    }
    static func mustReject(_ bytes: Data, _ label: String) {
        do {
            _ = try GhostlineWAVInspector.inspect(bytes)
            fatalError("Expected rejection: " + label)
        } catch is GhostlineWAVInspector.Failure {
            print("PASS rejected " + label)
        } catch {
            fatalError("Unexpected failure for " + label + ": " + String(describing: error))
        }
    }
    static func main() throws {
        let valid = wav([0, 100, -200, 300, -400, 10])
        let facts = try GhostlineWAVInspector.inspect(valid)
        precondition(facts.sampleRate == 16_000)
        precondition(facts.audioFrames == 6)
        precondition(facts.bitsPerSample == 16 && facts.channels == 1)
        print("PASS valid PCM WAV")
        mustReject(wav(Array(repeating: 0, count: 16)), "silent PCM")
        mustReject(Data(valid.dropLast()), "truncated RIFF")
        var invalid = valid
        invalid.replaceSubrange(0..<4, with: Data("FORM".utf8))
        mustReject(invalid, "non-RIFF container")
        var wrongAlignment = valid
        wrongAlignment[32] = 4
        mustReject(wrongAlignment, "wrong block alignment")
        var badChunkSize = valid
        badChunkSize[40] = 255
        mustReject(badChunkSize, "out-of-bounds WAV data chunk")
        print("GHOSTLINE WAV inspector tests passed; these do not establish listening or voice identity.")
    }
}
