import SwiftUI
import AVFoundation

@main struct VoiceMatrixApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
                .preferredColorScheme(.dark)
                .tint(Color(red: 0.72, green: 0.47, blue: 1))
        }
    }
}

struct RootView: View {
    var body: some View {
        TabView {
            NavigationStack { SpeechStudioView() }
                .tabItem { Label("Speak", systemImage: "text.bubble.fill") }
            NavigationStack { VoiceChangerView() }
                .tabItem { Label("Change", systemImage: "waveform.path") }
            NavigationStack { VoiceLibraryView() }
                .tabItem { Label("Voices", systemImage: "square.grid.2x2.fill") }
            NavigationStack { AboutView() }
                .tabItem { Label("About", systemImage: "info.circle") }
        }
    }
}

struct StudioHeader: View {
    let title: String
    let subtitle: String
    let symbol: String
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Image(systemName: symbol)
                    .font(.system(size: 33, weight: .semibold))
                    .foregroundStyle(.purple)
                Text(title).font(.title.bold())
            }
            Text(subtitle).foregroundStyle(.secondary).font(.subheadline)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.purple.opacity(0.13), in: RoundedRectangle(cornerRadius: 20))
    }
}

struct AboutView: View {
    var body: some View {
        Form {
            Section {
                StudioHeader(title: "VoiceMatrix", subtitle: "A fresh, lightweight English voice studio.", symbol: "waveform")
            }
            Section("Actual capabilities") {
                Label("iOS on-device text-to-speech with installed English voices", systemImage: "checkmark.circle")
                Label("Record, transform, preview, and export your speech", systemImage: "checkmark.circle")
                Label("Nine original audio effects; none impersonates a person", systemImage: "checkmark.circle")
                Label("Offline processing after app installation", systemImage: "checkmark.circle")
            }
            Section("500-voice catalog goal") {
                Text("The target is 500 permission-cleared, actually playable voices. Catalog listings, actor names, and effect presets are not counted as confirmed voice replicas. Available iOS voices depend on which speech voices the device has installed. Any future imported model needs a compatible runtime, lawful use rights, and on-device sound tests.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Section("Safety and permissions") {
                Text("Use voice likenesses only with appropriate authorization. This app does not download celebrity, singer, cartoon-character, or horror-actor replicas, and does not send recordings to servers.")
                    .font(.footnote)
            }
        }
        .navigationTitle("About")
    }
}
