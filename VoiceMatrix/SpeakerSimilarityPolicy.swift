import Foundation
/// A numeric diagnostic only. No identity, likeness or acceptance threshold.
enum SpeakerSimilarityPolicy {
    enum Failure: Error { case dimensions, invalidEmbedding }
    static func cosine(_ reference: [Float], _ generated: [Float]) throws -> Double {
        guard reference.count == 256, generated.count == 256 else { throw Failure.dimensions }
        guard reference.allSatisfy({$0.isFinite}), generated.allSatisfy({$0.isFinite}) else { throw Failure.invalidEmbedding }
        let a=reference.map(Double.init), b=generated.map(Double.init)
        let na=sqrt(a.reduce(0){$0+$1*$1}), nb=sqrt(b.reduce(0){$0+$1*$1})
        guard na.isFinite, nb.isFinite, na>0, nb>0 else { throw Failure.invalidEmbedding }
        let value=zip(a,b).reduce(0){$0+($1.0/na)*($1.1/nb)}
        guard value.isFinite else { throw Failure.invalidEmbedding }
        return min(1,max(-1,value))
    }
}
