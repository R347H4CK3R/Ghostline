import SwiftUI
import AVFoundation

struct SoundStyle: Identifiable, Hashable {
    let id: String
    let title: String
    let detail: String
    let pitch: Float
    let rate: Float
    static let all: [SoundStyle] = [
        .init(id:"normal",title:"My Normal Voice",detail:"No changes",pitch:0,rate:1),
        .init(id:"monster",title:"Deep Monster",detail:"Deep and slow",pitch:-650,rate:0.82),
        .init(id:"robot",title:"Friendly Robot",detail:"Steady lower tone",pitch:-250,rate:1),
        .init(id:"cartoon",title:"Tiny Cartoon",detail:"High and bouncy",pitch:600,rate:1.17),
        .init(id:"ghost",title:"Spooky Ghost",detail:"Low and mysterious",pitch:-390,rate:0.77),
        .init(id:"alien",title:"Alien Visitor",detail:"High and slow",pitch:400,rate:0.9),
        .init(id:"announcer",title:"Radio Announcer",detail:"Crisp and brisk",pitch:-130,rate:1.08),
        .init(id:"giant",title:"Giant Creature",detail:"Very deep",pitch:-840,rate:0.7),
        .init(id:"sprite",title:"Speedy Sprite",detail:"Bright and fast",pitch:450,rate:1.35)
    ]
}

@MainActor final class ChangerEngine: NSObject, ObservableObject {
    @Published var recording = false
    @Published var playing = false
    @Published var status = "Tap Record to start."
    @Published var recorded: URL?
    @Published var exported: URL?
    @Published var style = SoundStyle.all[0]
    private var recorder: AVAudioRecorder?
    private var audioEngine: AVAudioEngine?
    private var node: AVAudioPlayerNode?

    func startRecording() async {
        let permitted = await withCheckedContinuation { (answer: CheckedContinuation<Bool, Never>) in
            AVAudioApplication.requestRecordPermission { answer.resume(returning: $0) }
        }
        guard permitted else {
            status = "Allow microphone access in iPhone Settings to record."
            return
        }
        stopPlayback()
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker])
            try session.setActive(true)
            let target = FileManager.default.temporaryDirectory
                .appendingPathComponent("voicematrix-" + UUID().uuidString + ".caf")
            let configuration: [String:Any] = [
                AVFormatIDKey: Int(kAudioFormatLinearPCM),
                AVSampleRateKey: 44100,
                AVNumberOfChannelsKey: 1,
                AVLinearPCMBitDepthKey: 16,
                AVLinearPCMIsFloatKey: false
            ]
            let microphone = try AVAudioRecorder(url: target, settings: configuration)
            guard microphone.record() else { status = "The microphone could not start."; return }
            recorder = microphone
            recorded = target
            exported = nil
            recording = true
            status = "Recording. Speak now, then tap STOP."
        } catch {
            status = "Recording failed. Check microphone permission and try again."
        }
    }

    func stopRecording() {
        recorder?.stop()
        recorder = nil
        recording = false
        status = recorded == nil ? "No recording saved." : "Saved. Choose a sound, then tap Listen."
    }

    func listen() {
        guard let recorded else { status = "Record something first."; return }
        stopPlayback()
        do {
            let file = try AVAudioFile(forReading: recorded)
            let engine = AVAudioEngine()
            let player = AVAudioPlayerNode()
            let effect = AVAudioUnitTimePitch()
            effect.pitch = style.pitch
            effect.rate = style.rate
            engine.attach(player)
            engine.attach(effect)
            engine.connect(player, to: effect, format: file.processingFormat)
            engine.connect(effect, to: engine.mainMixerNode, format: file.processingFormat)
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [.defaultToSpeaker])
            try AVAudioSession.sharedInstance().setActive(true)
            try engine.start()
            player.scheduleFile(file, at: nil)
            player.play()
            audioEngine = engine
            node = player
            playing = true
            status = "Playing " + style.title + ". Tap Stop to finish early."
        } catch {
            status = "Could not play the recording."
            stopPlayback()
        }
    }

    func stopPlayback() {
        node?.stop()
        audioEngine?.stop()
        node = nil
        audioEngine = nil
        playing = false
    }

    func prepareOriginal() {
        guard let recorded else { status = "Make a recording first."; return }
        exported = recorded
        status = "Original audio ready to share. Effect export is not in this first test build."
    }
}

struct VoiceChangerView: View {
    @StateObject private var audio = ChangerEngine()
    var body: some View {
        Form {
            Section {
                StudioHeader(title:"Voice Changer",subtitle:"Record your own voice and hear it with an original effect. All processing happens on your phone.",symbol:"mic.fill")
            }
            Section("1. Record your voice") {
                Button {
                    if audio.recording { audio.stopRecording() }
                    else { Task { await audio.startRecording() } }
                } label: {
                    Label(audio.recording ? "STOP RECORDING" : "RECORD MY VOICE", systemImage: audio.recording ? "stop.fill" : "mic.fill")
                        .frame(maxWidth:.infinity,minHeight:60).font(.title3.bold())
                }
                .buttonStyle(.borderedProminent)
                .tint(audio.recording ? .red : .purple)
                Text("Say a short sentence, then tap Stop Recording.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("2. Choose a voice effect") {
                ForEach(SoundStyle.all) { sound in
                    Button {
                        audio.stopPlayback()
                        audio.style = sound
                    } label: {
                        HStack {
                            VStack(alignment:.leading,spacing:4) {
                                Text(sound.title).font(.headline)
                                Text(sound.detail).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            if audio.style.id == sound.id {
                                Image(systemName:"checkmark.circle.fill").foregroundStyle(.purple)
                            }
                        }.contentShape(Rectangle())
                    }.buttonStyle(.plain)
                }
                Text("Original fictional effects. These are not official character or celebrity voices.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("3. Listen to your new sound") {
                Button { audio.listen() } label: {
                    Label("LISTEN",systemImage:"play.fill")
                        .frame(maxWidth:.infinity,minHeight:54).font(.title3.bold())
                }.buttonStyle(.borderedProminent)
                    .disabled(audio.recorded == nil || audio.recording)
                Button("STOP PLAYBACK") { audio.stopPlayback() }.disabled(!audio.playing)
            }
            Section("4. Save original recording") {
                Button("Prepare original audio") { audio.prepareOriginal() }
                    .disabled(audio.recorded == nil || audio.recording)
                if let source = audio.exported {
                    ShareLink(item: source) {
                        Label("SAVE OR SHARE RECORDING",systemImage:"square.and.arrow.up")
                    }
                }
                Text("Preview effects work offline. The first test build exports only the unmodified recording; converted-audio export is not yet implemented.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Status") { Text(audio.status).font(.footnote) }
        }
        .navigationTitle("Change")
        .onDisappear {
            if audio.recording { audio.stopRecording() }
            audio.stopPlayback()
        }
    }
}
