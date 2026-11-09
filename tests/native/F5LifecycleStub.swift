import Foundation
public struct F5TTSSynthesisOptions { public init(steps: Int, seed: UInt64) throws {} }
public final class F5TTSTokenizer { public func encode(_ text: String) throws -> [Int] { Array(repeating: 1, count: text.count) } }
// Test boundary only: avoids loading 700 MB and invoking Metal for lifecycle cases.
public final class F5TTSModel: @unchecked Sendable {
    public static var loads = 0
    public static var unloads = 0
    public let tokenizer = F5TTSTokenizer()
    public static func fromBundle(_ url: URL) async throws -> F5TTSModel { loads += 1; return F5TTSModel() }
    public func unload() { Self.unloads += 1 }
    public func generate(text: String, referenceAudio: URL, referenceText: String, options: F5TTSSynthesisOptions) async throws -> [Float] {
        return (0..<4800).map { 0.1 * sin(Float($0) * 0.1) }
    }
}
