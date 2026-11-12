import Foundation

/// Intelligibility evidence is not speaker identity, diarization or likeness proof.
enum LocalStudioEvidence {
    static func words(_ text: String) -> [String] {
        text.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
    }
    static func usableTranscript(_ text: String) -> Bool {
        let count = words(text).count
        return (3...100).contains(count) && text.utf8.count <= 700 &&
            !text.contains("♪") && !text.contains("♫") && !text.contains("[") && !text.contains("]")
    }
    static func wordErrorRate(expected: String, actual: String) -> Double {
        let a = words(expected), b = words(actual)
        guard !a.isEmpty, a.count <= 200, b.count <= 200 else { return 1 }
        var row = Array(0...b.count)
        for (i, word) in a.enumerated() {
            var next = [i + 1]
            for (j, other) in b.enumerated() { next.append(min(next[j] + 1, row[j + 1] + 1, row[j] + (word == other ? 0 : 1))) }
            row = next
        }
        return Double(row[b.count]) / Double(a.count)
    }
    static func windows(duration: Double) -> [(start: Double, seconds: Double)] {
        guard duration.isFinite, duration >= 3, duration <= 1800 else { return [] }
        return stride(from: 0.0, through: max(0, duration - 3), by: 6).map { ($0, min(8, duration - $0)) }
    }
}
