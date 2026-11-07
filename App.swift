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
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                HomeView(onSpeak: { selectedTab = 1 }, onChange: { selectedTab = 2 })
            }
            .tabItem { Label("Home", systemImage: "house.fill") }.tag(0)

            NavigationStack { SpeechStudioView() }
                .tabItem { Label("Make Speech", systemImage: "text.bubble.fill") }.tag(1)

            NavigationStack { VoiceChangerView() }
                .tabItem { Label("Change Voice", systemImage: "waveform.path") }.tag(2)

            NavigationStack { VoiceLibraryView() }
                .tabItem { Label("Voices", systemImage: "square.grid.2x2.fill") }.tag(3)

            NavigationStack { AboutView() }
                .tabItem { Label("Help", systemImage: "questionmark.circle") }.tag(4)
        }
    }
}

struct HomeView: View {
    let onSpeak: () -> Void
    let onChange: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack(spacing: 14) {
                    Image(systemName: "waveform.circle.fill")
                        .font(.system(size: 52))
                        .foregroundStyle(.purple)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("VoiceMatrix").font(.largeTitle.bold())
                        Text("Your private, offline voice studio")
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 12)

                Text("What would you like to do?")
                    .font(.title2.bold())

                Button(action: onSpeak) {
                    VStack(alignment: .leading, spacing: 10) {
                        Image(systemName: "text.bubble.fill").font(.system(size: 36))
                        Text("MAKE SPEECH").font(.title.bold())
                        Text("Type words and hear them spoken aloud.")
                            .font(.body)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(24)
                    .frame(minHeight: 166)
                }
                .buttonStyle(.borderedProminent)
                .tint(.purple)
                .accessibilityLabel("Make Speech. Type words and hear them spoken aloud.")

                Button(action: onChange) {
                    VStack(alignment: .leading, spacing: 10) {
                        Image(systemName: "mic.fill").font(.system(size: 36))
                        Text("CHANGE MY VOICE").font(.title.bold())
                        Text("Record your voice and try original sound effects.")
                            .font(.body)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(24)
                    .frame(minHeight: 166)
                }
                .buttonStyle(.borderedProminent)
                .tint(Color(red: 0.28, green: 0.36, blue: 0.75))
                .accessibilityLabel("Change My Voice. Record and preview sound effects.")

                Text("No account needed. This version uses English voices already installed on your iPhone. Neural voice packs and effect export are still in development.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            .padding(22)
        }
        .background(Color(red: 0.065, green: 0.045, blue: 0.12))
        .navigationTitle("Home")
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
                Label("Record, preview effects, and share original audio", systemImage: "checkmark.circle")
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
