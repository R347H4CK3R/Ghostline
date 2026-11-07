import SwiftUI
import AVFoundation

@MainActor final class SpeakEngine: NSObject, ObservableObject, AVSpeechSynthesizerDelegate {
    @Published var message = "Pick a voice. Type a sentence. Tap Speak."
    @Published var voiceID = ""
    @Published var speaking = false
    @Published var rate: Float = 0.48
    @Published var pitch: Float = 1.0
    private let speaker = AVSpeechSynthesizer()
    var voices: [AVSpeechSynthesisVoice] {
        AVSpeechSynthesisVoice.speechVoices().filter { $0.language.hasPrefix("en-") }
            .sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }
    override init() {
        super.init()
        speaker.delegate = self
        voiceID = voices.first(where: { $0.language == "en-US" })?.identifier ?? voices.first?.identifier ?? ""
    }
    func speak(_ phrase: String) {
        let words = phrase.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !words.isEmpty else { message = "Type your sentence first."; return }
        guard let voice = voices.first(where: { $0.identifier == voiceID }) else {
            message = "No installed English speech voice. Add one from iPhone Settings."
            return
        }
        speaker.stopSpeaking(at: .immediate)
        let text = AVSpeechUtterance(string: words)
        text.voice = voice
        text.rate = rate
        text.pitchMultiplier = pitch
        text.volume = 1
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default, options: [.defaultToSpeaker])
            try AVAudioSession.sharedInstance().setActive(true)
        } catch {
            message = "Audio unavailable. Check sound settings."
            return
        }
        speaking = true
        speaker.speak(text)
        message = "Speaking with the selected English voice."
    }
    func stop() {
        speaker.stopSpeaking(at: .immediate)
        speaking = false
        message = "Stopped. Type another sentence or try a different voice."
    }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.speaking = false; self?.message = "Finished speaking." }
    }
    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in self?.speaking = false }
    }
}
struct SpeechStudioView: View {
    @StateObject private var engine = SpeakEngine()
    @State private var words = "Hello! I can speak without an internet connection."
    var body: some View {
        Form {
            Section {
                StudioHeader(title: "Text to Speech", subtitle: "Write what you want to hear. Everything happens on your iPhone.", symbol: "text.bubble.fill")
            }
            Section("1. Choose an English voice") {
                if engine.voices.isEmpty {
                    Text("No English voice is installed. Open iPhone Settings, then Accessibility and Spoken Content.")
                        .foregroundStyle(.secondary)
                } else {
                    Picker("Voice", selection: $engine.voiceID) {
                        ForEach(engine.voices, id: \.identifier) { voice in
                            Text("\(voice.name) (\(voice.language))").tag(voice.identifier)
                        }
                    }
                    Text("\(engine.voices.count) English voices installed on this device.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            Section("2. Type your words") {
                TextEditor(text: $words)
                    .frame(minHeight: 120)
                    .accessibilityLabel("Words to be spoken")
                Button("Clear words") { words = "" }.disabled(words.isEmpty)
            }
            Section("3. Tap Speak") {
                Button { engine.speak(words) } label: {
                    Label("SPEAK MY WORDS", systemImage: "play.fill")
                        .frame(maxWidth: .infinity, minHeight: 54).font(.title3.bold())
                }
                .buttonStyle(.borderedProminent)
                .disabled(words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || engine.voices.isEmpty)
                Button("STOP SPEAKING") { engine.stop() }.disabled(!engine.speaking)
                Text(engine.message).font(.footnote).foregroundStyle(.secondary)
            }
            Section("Optional sound controls") {
                Text("Speaking speed")
                Slider(value: $engine.rate, in: 0.35...0.6)
                Text("Voice pitch")
                Slider(value: $engine.pitch, in: 0.7...1.5)
                Text("These adjustments change sound but do not clone a person.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }.navigationTitle("Speak")
    }
}
