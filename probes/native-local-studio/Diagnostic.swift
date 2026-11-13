import Foundation
import AVFoundation
import CryptoKit
import Metal

/// Exercises the real production coordinator and stores, not a parallel pipeline.
@main struct LocalStudioDiagnostic {
    enum Failure: Error { case arguments, fixture, timeout, pipeline, evidence, preservation }
    struct Report: Codable {
        let sourceCommit: String
        let fixtureSHA256: String
        let sourceRetainedSHA256: String
        let importedIDs: [String]
        let events: [LocalVideoStudio.Event]
        let cancellationRetainedSource: Bool
        let resumeCompleted: Bool
        let freshStoreReloadPreservedIDs: Bool
        let priorProfilePreserved: Bool
        let newSpeechSHA256: String
        let newSpeechWordErrorRate: Double
        let evidenceFiles: [String]
        let physicalIPhoneVerified = false
        let likenessVerified = false
        let characterIdentificationVerified = false
        let pipelineKind = "Actual production local coordinator on macOS; synthetic neutral fixture"
    }
    static func digest(_ url: URL) throws -> String {
        SHA256.hash(data: try Data(contentsOf: url)).map { String(format:"%02x",$0) }.joined()
    }
    @MainActor static func settle(_ studio: LocalVideoStudio, seconds: Double = 1200) async throws {
        let deadline=Date().addingTimeInterval(seconds)
        while studio.busy {
            guard Date()<deadline else { studio.cancel(); throw Failure.timeout }
            try await Task.sleep(for:.milliseconds(100))
        }
    }
    @MainActor static func main() async throws {
        guard CommandLine.arguments.count==7, MTLCreateSystemDefaultDevice() != nil else { throw Failure.arguments }
        let resources=URL(fileURLWithPath:CommandLine.arguments[1],isDirectory:true)
        let fixture=URL(fileURLWithPath:CommandLine.arguments[2])
        let priorCollection=URL(fileURLWithPath:CommandLine.arguments[3],isDirectory:true)
        let work=URL(fileURLWithPath:CommandLine.arguments[4],isDirectory:true).resolvingSymlinksInPath()
        let report=URL(fileURLWithPath:CommandLine.arguments[5])
        let commit=CommandLine.arguments[6]
        guard commit.range(of:"^[a-f0-9]{40}$",options:.regularExpression) != nil,
              !FileManager.default.fileExists(atPath:work.path) else { throw Failure.arguments }
        try FileManager.default.createDirectory(at:work,withIntermediateDirectories:true)
        let decoded=try AVAudioFile(forReading:fixture)
        let seconds=Double(decoded.length)/decoded.processingFormat.sampleRate
        guard (8...60).contains(seconds),decoded.processingFormat.channelCount==1 else { throw Failure.fixture }
        let fixtureHash=try digest(fixture)
        let support=work.appendingPathComponent("Support",isDirectory:true)
        let store=CharacterFolderStore(root:support.appendingPathComponent("CharacterReferences",isDirectory:true))
        let prior=try await store.importCollection(at:priorCollection)
        guard prior.count==1 else { throw Failure.fixture }
        let priorID=prior[0].id,priorHash=prior[0].referenceSHA256
        let library=CharacterLibrary(supportRoot:support,f5Bundle:resources.appendingPathComponent("F5TTS"))
        await library.loadAndRefresh()
        let audio=AudioStore(recordingRoot:work.appendingPathComponent("Recordings",isDirectory:true))
        let speech=SpeechStudio()
        let studio=LocalVideoStudio(root:work.appendingPathComponent("Jobs",isDirectory:true),
            asrBundle:resources.appendingPathComponent("ParakeetASR"),
            f5Bundle:resources.appendingPathComponent("F5TTS"),
            speakerBundle:resources.appendingPathComponent("Diarization"))
        do {
            studio.start(fixture,authorized:true,library:library,audio:audio,speech:speech)
            let cancelDeadline=Date().addingTimeInterval(120)
            while studio.busy && studio.current?.sourceFile==nil {
                guard Date()<cancelDeadline else { throw Failure.timeout }
                try await Task.sleep(for:.milliseconds(10))
            }
            guard studio.busy, let job=studio.current,let name=job.sourceFile else { throw Failure.pipeline }
            studio.cancel()
            try await settle(studio)
            let retained=work.appendingPathComponent("Jobs/"+job.id.uuidString.lowercased()+"/"+name)
            guard try digest(retained)==fixtureHash, !audio.processingInUse, !library.busy else { throw Failure.preservation }
            studio.resume(library:library,audio:audio,speech:speech)
            try await settle(studio)
            guard studio.current?.completed == true,let completed=studio.current,
                  let ids=completed.speakerVoiceIDs,!ids.isEmpty, !audio.processingInUse,!library.busy else { throw Failure.pipeline }
            let folder=retained.deletingLastPathComponent()
            let files=try FileManager.default.contentsOfDirectory(atPath:folder.path)
            guard let similarity=completed.matchingSimilarity,
                  similarity.report.referenceSHA256 == (try digest(folder.appendingPathComponent(similarity.referenceFile))),
                  similarity.report.generatedSHA256 == (try digest(folder.appendingPathComponent(similarity.previewFile))) else { throw Failure.evidence }
            for prefix in ["similarity-","diarization-","quality-","transcription-evidence-","preview-asr-evidence-","preview-"] {
                guard files.contains(where:{$0.hasPrefix(prefix)}) else { throw Failure.evidence }
            }
            guard let preview=studio.preview else { throw Failure.evidence }
            let wave=try AVAudioFile(forReading:preview)
            guard wave.length>0,let buffer=AVAudioPCMBuffer(pcmFormat:wave.processingFormat,frameCapacity:AVAudioFrameCount(wave.length)) else { throw Failure.evidence }
            try wave.read(into:buffer)
            guard buffer.frameLength>0 else { throw Failure.evidence }
            let reloaded=CharacterLibrary(supportRoot:support,f5Bundle:resources.appendingPathComponent("F5TTS"))
            await reloaded.loadAndRefresh()
            let expected=Set(ids.values)
            guard expected.isSubset(of:Set(reloaded.profiles.map(\.id))),
                  reloaded.profiles.contains(where:{$0.id==priorID && $0.referenceSHA256==priorHash}),
                  try digest(retained)==fixtureHash,try digest(fixture)==fixtureHash else { throw Failure.preservation }
            let beforeCount=reloaded.profiles.count
            studio.resume(library:reloaded,audio:audio,speech:speech)
            try await settle(studio)
            guard reloaded.profiles.count==beforeCount else { throw Failure.preservation }
            // Generate new words through the reloaded production catalog, not the preview adapter.
            reloaded.selectedID=expected.sorted()[0]
            let newText="Please close the window and bring the notebook."
            reloaded.speak(newText,audio:audio,studio:speech)
            let speechDeadline=Date().addingTimeInterval(600)
            while reloaded.busy {
                guard Date()<speechDeadline else { reloaded.cancel(); throw Failure.timeout }
                try await Task.sleep(for:.milliseconds(100))
            }
            guard let freshSpeech=reloaded.output,!audio.processingInUse,
                  reloaded.outputCharacterID==reloaded.selectedID,
                  reloaded.profiles.first(where:{$0.id==reloaded.selectedID})?.referenceSHA256==reloaded.outputReferenceHash else { throw Failure.pipeline }
            // beginLocalGeneration uses the real ownership fence and unloads warm F5 before ASR.
            let verificationOwner=try await reloaded.beginLocalGeneration()
            defer { reloaded.endLocalGeneration(verificationOwner) }
            let recognizer=OnDeviceTranscription(bundle:resources.appendingPathComponent("ParakeetASR"))
            let words=try await recognizer.transcribe(freshSpeech)
            reloaded.endLocalGeneration(verificationOwner)
            let wer=LocalStudioEvidence.wordErrorRate(expected:newText,actual:words)
            guard wer<=0.1,let detail=recognizer.lastEvidence,
                  detail.inputSHA256 == (try digest(freshSpeech)) else { throw Failure.evidence }
            let finalSpeech=work.appendingPathComponent("new-speech.wav")
            try FileManager.default.copyItem(at:freshSpeech,to:finalSpeech)
            try JSONEncoder().encode(detail).write(to:work.appendingPathComponent("new-speech-asr.json"),options:.atomic)
            let result=Report(sourceCommit:commit,fixtureSHA256:fixtureHash,sourceRetainedSHA256:try digest(retained),importedIDs:expected.sorted(),events:completed.events,cancellationRetainedSource:true,resumeCompleted:true,freshStoreReloadPreservedIDs:true,priorProfilePreserved:true,newSpeechSHA256:try digest(finalSpeech),newSpeechWordErrorRate:wer,evidenceFiles:files.sorted())
            let encoder=JSONEncoder();encoder.outputFormatting=[.prettyPrinted,.sortedKeys]
            try encoder.encode(result).write(to:report,options:.atomic)
            print("Actual local coordinator completed with retained source, cancellation/resume and persisted imports. iPhone behavior and likeness are unverified.")
        } catch {
            // A failed native gate must expose the actual final stage in CI logs.
            if let job=studio.current {
                let lines = ["Local pipeline failed at stage: " + job.stage + "; status: " + job.message] + job.events.suffix(12).map { $0.stage + ": " + $0.message }
                try? FileHandle.standardError.write(contentsOf: Data((lines.joined(separator:"\n") + "\n").utf8))
            }
            studio.cancel()
            try? await settle(studio,seconds:120)
            if let job=studio.current { try? JSONEncoder().encode(job).write(to:report.deletingLastPathComponent().appendingPathComponent("failed-job.json"),options:.atomic) }
            throw error
        }
    }
}
