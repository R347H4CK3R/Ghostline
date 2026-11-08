import Foundation
import AVFoundation
@main struct Inputs {
 static func main() throws {
  for (index,path) in CommandLine.arguments.dropFirst().enumerated() {
   let url=URL(fileURLWithPath:path), f=try AVAudioFile(forReading:url)
   print("INPUT \(path) seconds=\(Double(f.length)/f.processingFormat.sampleRate) rate=\(f.processingFormat.sampleRate) frames=\(f.length)")
   do { let samples=try ConversionAudio.readMono(url,minimumSeconds:index==0 ? 0.15 : 0.5,isReference:index==1);print("RESAMPLED count=\(samples.count) seconds=\(Double(samples.count)/22050)") }
   catch {print("INPUT FAILED \(path): \(error) \(error.localizedDescription)");throw error}
  }
 }
}
