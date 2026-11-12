import Foundation

/// Token softmax scores are not calibrated transcript correctness probabilities
/// and are not comparable to Apple's speech-segment confidence values.
enum BundledASRPolicy {
    static let minimumTokenMean: Float = 0.35
    static func admittedTokenMean(_ scores: [Float]) -> Float? {
        guard (1...4096).contains(scores.count), scores.allSatisfy({ $0.isFinite && (0...1).contains($0) }) else { return nil }
        let mean = scores.reduce(0, +) / Float(scores.count)
        return mean >= minimumTokenMean ? mean : nil
    }
}
