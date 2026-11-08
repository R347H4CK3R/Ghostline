import Foundation
import AVFoundation
import CoreML
import CryptoKit
import Darwin
@main struct CoreMLProbe {
 static func main() async throws {
  setbuf(stdout,nil)
  let a=CommandLine.arguments;guard a.count==4 else {fatalError("Expected source reference output")}
  let root=URL(fileURLWithPath:a[3]);try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
  let source=URL(fileURLWithPath:a[1]),reference=URL(fileURLWithPath:a[2])
  let hash:(URL)throws->String={SHA256.hash(data:try Data(contentsOf:$0)).map{String(format:"%02x",$0)}.joined()}
  for (name,units) in [("cpu",MLComputeUnits.cpuOnly),("cpu-and-gpu",MLComputeUnits.cpuAndGPU)] {
   let out=root.appendingPathComponent(name);try FileManager.default.createDirectory(at:out,withIntermediateDirectories:true)
   let converter=OfflineVoiceConverter(computeUnits:units);let started=Date()
   print("Starting \(name) target encoding")
   let target=try await converter.extractEmbedding(from:reference)
   print("Starting \(name) conversion")
   let file=out.appendingPathComponent("reference-conditioned-conversion.wav")
   let result=try await converter.convert(source:source,target:target,destination:file){print($0)}
   let report:[String:Any]=["sharedModelManifestSHA256":try hash(Bundle.main.url(forResource:"OpenVoice",withExtension:nil)!.appendingPathComponent("model-manifest.json")),"sourceAudioSHA256":try hash(source),"referenceAudioSHA256":try hash(reference),"outputSHA256":try hash(file),"sourceSeconds":result.sourceSeconds,"outputSeconds":result.outputSeconds,"expectedText":"I found a strange device near the portal.","computeUnits":name,"wallSeconds":Date().timeIntervalSince(started),"physicalDeviceVerified":false,"likenessVerified":false,"scope":"Hosted macOS CoreML diagnostic using actual production converter sources"]
   try JSONSerialization.data(withJSONObject:report,options:[.sortedKeys,.prettyPrinted]).write(to:out.appendingPathComponent("conversion-result.json"),options:.atomic)
   await converter.unload();print("Completed \(name)")
  }
 }
}
