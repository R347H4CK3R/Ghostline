import Foundation

enum F5ChunkError: LocalizedError {
    case invalidReference, emptyText, wordTooLong, jobTooLong
    var errorDescription: String? {
        switch self {
        case .invalidReference: return "This reference needs a clearer, shorter speech sample. Your saved reference was kept."
        case .emptyText: return "Type the words you want your character to say."
        case .jobTooLong: return "This job exceeds about 30 minutes of speech before speed changes. Split it into smaller jobs; no words were removed."
        case .wordTooLong: return "This message cannot fit this reference safely. Try shorter words or a reference with more continuous speech."
        }
    }
}

// Matches the upstream F5 duration formula and its Python22second batch budget.
// Dynamic programming keeps complete words, including short-text speed behavior.
enum F5SpeechChunks {
    static let maximumJobSeconds: Double = 1800
    static func normalizedReference(_ text: String) -> String {
        var result = text
        if !result.hasSuffix(". "), !result.hasSuffix("。") { result += result.hasSuffix(".") ? " " : ". " }
        if result.last?.utf8.count == 1 { result += " " }
        return result
    }
    static func validateTokenCount(_ count: Int) throws {
        // The native sampler also takes max(duration, tokenIds.count + 1).
        guard count > 0, count <= 2061 else { throw F5ChunkError.wordTooLong }
    }
    static func estimatedSeconds(text: String, referenceText: String, referenceSeconds: Double) -> Double {
        let referenceFrames = Int(referenceSeconds * 24000) / 256
        let referenceBytes = max(normalizedReference(referenceText).utf8.count, 1)
        let speed: Float = text.utf8.count < 10 ? 0.3 : 1
        let extraFrames = Int(Float(referenceFrames) / Float(referenceBytes) * Float(text.utf8.count) / speed)
        return Double(max(referenceFrames + extraFrames, referenceFrames + 1)) * 256 / 24000
    }
    static func plan(text: String, referenceText: String, referenceSeconds: Double) throws -> [String] {
        guard referenceSeconds.isFinite, (0.5...15.01).contains(referenceSeconds),
              !referenceText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              referenceText.utf8.count <= 512 else { throw F5ChunkError.invalidReference }
        let words = text.split(whereSeparator: \.isWhitespace).map(String.init)
        guard !words.isEmpty else { throw F5ChunkError.emptyText }
        guard Double(text.utf8.count) * referenceSeconds / Double(normalizedReference(referenceText).utf8.count) <= maximumJobSeconds else { throw F5ChunkError.jobTooLong }
        var costs = [Int](repeating: Int.max, count: words.count + 1)
        var previous = [Int](repeating: -1, count: words.count + 1)
        costs[0] = 0
        let maximumBytes = Double(normalizedReference(referenceText).utf8.count) / referenceSeconds * (22 - referenceSeconds)
        for end in 1...words.count {
            try Task.checkCancellation()
            var bytes = 0
            for start in stride(from: end - 1, through: 0, by: -1) {
                bytes += words[start].utf8.count + (start == end - 1 ? 0 : 1)
                // Beyond the normal-speed budget no still-longer segment can fit.
                if Double(bytes) > maximumBytes + 1 { break }
                guard costs[start] != Int.max else { continue }
                let referenceFrames = Int(referenceSeconds * 24000) / 256
                let speed: Float = bytes < 10 ? 0.3 : 1
                let frames = referenceFrames + Int(Float(referenceFrames) / Float(normalizedReference(referenceText).utf8.count) * Float(bytes) / speed)
                guard Double(max(frames, referenceFrames + 1)) * 256 / 24000 <= 22 else { continue }
                if costs[start] + 1 < costs[end] {
                    costs[end] = costs[start] + 1; previous[end] = start
                }
            }
        }
        guard previous[words.count] >= 0 else { throw F5ChunkError.wordTooLong }
        var chunks: [String] = []; var end = words.count
        while end > 0 { let start = previous[end]; chunks.append(words[start..<end].joined(separator: " ")); end = start }
        let ordered = Array(chunks.reversed())
        let seconds = ordered.reduce(0.0) { $0 + max(0, estimatedSeconds(text: $1, referenceText: referenceText, referenceSeconds: referenceSeconds) - referenceSeconds) + 1 }
        guard seconds <= maximumJobSeconds else { throw F5ChunkError.jobTooLong }
        return ordered
    }
}
