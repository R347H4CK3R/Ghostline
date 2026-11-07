import SwiftUI
import AVFoundation

struct VoiceCategory: Identifiable {
    let id: String
    let label: String
    let icon: String
    let detail: String
    static let categories: [VoiceCategory] = [
        .init(id: "Original", label: "Original Voices", icon: "waveform", detail: "Installed local English TTS voices"),
        .init(id: "Animation", label: "Animation", icon: "sparkles", detail: "Voice-style ideas; no character clones included"),
        .init(id: "Horror", label: "Horror", icon: "moon.stars.fill", detail: "Original monster/ghost effects in Voice Changer"),
        .init(id: "Film", label: "Movies & Film", icon: "film", detail: "Original narration, no film performer likenesses"),
        .init(id: "Television", label: "Television", icon: "tv", detail: "Original presenter-style voice demos"),
        .init(id: "Games", label: "Games", icon: "gamecontroller", detail: "Original game-dialogue and radio effects"),
        .init(id: "Anime", label: "Anime", icon: "star", detail: "Original English animation styles"),
        .init(id: "Performers", label: "Singers & Actors", icon: "music.mic", detail: "No unauthorized artist voice models")
    ]
}

struct VoiceLibraryView: View {
    var body: some View {
        List {
            Section {
                StudioHeader(title: "Voice Library", subtitle: "Only real, installed English speech voices are playable. Original effects are available in Change.", symbol: "square.grid.2x2.fill")
            }
            Section("On-device English TTS voices") {
                let voices = AVSpeechSynthesisVoice.speechVoices()
                    .filter { $0.language.hasPrefix("en-") }
                    .sorted { $0.name < $1.name }
                Text("\(voices.count) available on this device")
                    .font(.footnote).foregroundStyle(.secondary)
                ForEach(voices, id: \.identifier) { voice in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(voice.name).font(.headline)
                        Text("\(voice.language) • iOS installed speech voice")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if voices.isEmpty {
                    Text("No English speech voices are installed. Install an English system voice in iOS Settings.")
                }
            }
            Section("Browse creative categories") {
                ForEach(VoiceCategory.categories) { item in
                    NavigationLink {
                        CategoryDetails(category: item)
                    } label: {
                        Label(item.label, systemImage: item.icon)
                    }
                }
            }
        }
        .navigationTitle("Voices")
    }
}

struct CategoryDetails: View {
    let category: VoiceCategory
    var body: some View {
        List {
            Section {
                StudioHeader(title: category.label, subtitle: category.detail, symbol: category.icon)
                Text("This is a category, not a catalog of authorized real-person or copyrighted-character voice models.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Available functionality") {
                NavigationLink("Use installed English TTS voices") { SpeechStudioView() }
                NavigationLink("Transform your recording with original effects") { VoiceChangerView() }
            }
        }
        .navigationTitle(category.label)
    }
}
