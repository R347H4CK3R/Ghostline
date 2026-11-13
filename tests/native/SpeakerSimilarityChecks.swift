import Foundation
@main struct Checks {
 static func reject(_ a:[Float],_ b:[Float]) { do { _ = try SpeakerSimilarityPolicy.cosine(a,b); fatalError("invalid input accepted") } catch {} }
 static func main() throws {
  let one=[Float](repeating:1,count:256),negative=[Float](repeating:-7,count:256)
  let same=try SpeakerSimilarityPolicy.cosine(one,one);assert(abs(same-1)<1e-12)
  let opposite=try SpeakerSimilarityPolicy.cosine(one,negative);assert(abs(opposite+1)<1e-12)
  var a=[Float](repeating:0,count:256),b=a;a[0]=1;b[1]=1
  let perpendicular=try SpeakerSimilarityPolicy.cosine(a,b);assert(perpendicular==0)
  reject([],[]);reject(one,Array(one.dropLast()));reject([Float](repeating:0,count:256),one)
  a[0] = .nan;reject(a,one);a[0] = .infinity;reject(a,one)
  let large=try SpeakerSimilarityPolicy.cosine([Float](repeating:Float.greatestFiniteMagnitude,count:256),one);assert(abs(large-1)<1e-12)
  let tiny=try SpeakerSimilarityPolicy.cosine([Float](repeating:Float.leastNonzeroMagnitude,count:256),one);assert(abs(tiny-1)<1e-12)
  print("Similarity math passed: dimensions, finite/nonzero, scale, orthogonality and polarity")
 }
}
