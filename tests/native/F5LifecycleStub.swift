import Foundation
public struct F5TTSSynthesisOptions { public init(steps: Int, seed: UInt64) throws {} }
public final class F5TTSTokenizer { public func encode(_ text: String) throws -> [Int] { Array(repeating: 1, count: text.count) } }
public enum StubFailure: Error { case generation, unloaded }
public actor F5LifecycleGate {
    public var loadEntered = false
    public var generationEntered = false
    private var holdLoad = false
    private var holdGeneration = false
    private var failGeneration = false
    private var pendingLoad: CheckedContinuation<Void, Never>?
    private var pendingGeneration: CheckedContinuation<Void, Never>?
    public func configure(load: Bool = false, generation: Bool = false, fail: Bool = false) {
        holdLoad = load; holdGeneration = generation; failGeneration = fail
        loadEntered = false; generationEntered = false
    }
    public func enterLoad() async {
        loadEntered = true
        if holdLoad { await withCheckedContinuation { pendingLoad = $0 } }
    }
    public func enterGeneration() async throws {
        generationEntered = true
        if holdGeneration { await withCheckedContinuation { pendingGeneration = $0 } }
        if failGeneration { throw StubFailure.generation }
    }
    public func resumeLoad() { holdLoad = false; pendingLoad?.resume(); pendingLoad = nil }
    public func resumeGeneration() { holdGeneration = false; pendingGeneration?.resume(); pendingGeneration = nil }
}
// Only the heavy runtime boundary is replaced; the production adapter owns all lifecycle logic.
public final class F5TTSModel: @unchecked Sendable {
    public static var loads = 0
    public static var unloads = 0
    public static let gate = F5LifecycleGate()
    public let tokenizer = F5TTSTokenizer()
    private var loaded = true
    public static func fromBundle(_ url: URL) async throws -> F5TTSModel {
        loads += 1
        await gate.enterLoad()
        return F5TTSModel()
    }
    public func unload() { Self.unloads += 1; loaded = false }
    public func generate(text: String, referenceAudio: URL, referenceText: String, options: F5TTSSynthesisOptions) async throws -> [Float] {
        try await Self.gate.enterGeneration()
        guard loaded else { throw StubFailure.unloaded }
        return (0..<4800).map { 0.1 * sin(Float($0) * 0.1) }
    }
}
