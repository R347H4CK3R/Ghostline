import Foundation
import CryptoKit
@main struct SimilarityDiagnostic {
 enum Failure:Error {case arguments,incorrectResult,cancellation,fixture}
 static func main() async throws {
  guard CommandLine.arguments.count==6 else {throw Failure.arguments}
  let bundle=URL(fileURLWithPath:CommandLine.arguments[1]),one=URL(fileURLWithPath:CommandLine.arguments[2]),two=URL(fileURLWithPath:CommandLine.arguments[3]),out=URL(fileURLWithPath:CommandLine.arguments[4])
  let reference=try Data(contentsOf:one),generated=try Data(contentsOf:two)
  let service=SpeakerSimilarityService()
  let same=try await service.compare(referenceWAV:reference,generatedWAV:reference,bundle:bundle)
  guard abs(same.cosineSimilarity-1)<0.0001,same.referenceSHA256==same.generatedSHA256,!same.likenessVerified,!same.identityVerified else {throw Failure.incorrectResult}
  var prefixed=Data([0]);prefixed.append(reference)
  let sliced=try await service.compare(referenceWAV:prefixed.dropFirst(),generatedWAV:reference,bundle:bundle)
  guard sliced.referenceSHA256==same.referenceSHA256,abs(sliced.cosineSimilarity-1)<0.0001 else {throw Failure.incorrectResult}
  let different=try await service.compare(referenceWAV:reference,generatedWAV:generated,bundle:bundle)
  guard different.referenceSHA256 != different.generatedSHA256,(-1...1).contains(different.cosineSimilarity),!different.likenessVerified else {throw Failure.incorrectResult}
  let (started,signal)=AsyncStream<Void>.makeStream()
  let cancelled=Task {try await service.compare(referenceWAV:reference,generatedWAV:generated,bundle:bundle,progress:{_ in _ = signal.yield(())})}
  var iterator=started.makeAsyncIterator()
  guard await iterator.next() != nil else {throw Failure.cancellation}
  cancelled.cancel()
  do {_ = try await cancelled.value;throw Failure.cancellation} catch is CancellationError {}
  signal.finish()
  let recovered=try await service.compare(referenceWAV:reference,generatedWAV:reference,bundle:bundle)
  guard abs(recovered.cosineSimilarity-1)<0.0001 else {throw Failure.incorrectResult}
  do {_ = try await service.compare(referenceWAV:reference,generatedWAV:generated,bundle:bundle.appendingPathComponent("missing-model-bundle"));throw Failure.incorrectResult} catch LocalSpeakerDiarization.Failure.invalidBundle {}
  do {_ = try await service.compare(referenceWAV:Data(),generatedWAV:generated,bundle:bundle);throw Failure.incorrectResult} catch SpeakerSimilarityService.Failure.resourceBound {}
  guard try Data(contentsOf:one)==reference,try Data(contentsOf:two)==generated else {throw Failure.fixture}
  struct Evidence:Encodable {
   let sourceCommit:String
   let sameInput:SpeakerSimilarityService.Report
   let distinctInput:SpeakerSimilarityService.Report
   let cancellationRejected=true
   let cancellationRecoveryVerified=true
   let missingBundleRejected=true
   let invalidWAVRejected=true
   let slicedDataVerified=true
   let sourcesUnchanged=true
   let physicalIPhoneVerified=false
   let likenessVerified=false
   let label="Actual bundled-model similarity on installed macOS synthetic speech; no identity or likeness acceptance threshold"
  }
  let e=Evidence(sourceCommit:CommandLine.arguments[5],sameInput:same,distinctInput:different)
  let encoder=JSONEncoder();encoder.outputFormatting=[.prettyPrinted,.sortedKeys]
  try encoder.encode(e).write(to:out,options:.atomic)
  print("Actual speaker embedding comparison passed; likeness and physical iPhone not verified")
 }
}
