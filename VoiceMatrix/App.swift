import SwiftUI
import AVFoundation

@main struct VoiceMatrixApp: App {
    init() { TemporaryAudio.cleanPreviousSession() }
    @StateObject private var studio = SpeechStudio()
    @StateObject private var audio = AudioStore()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(studio).environmentObject(audio).preferredColorScheme(.dark).tint(.purple)
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didReceiveMemoryWarningNotification)) { _ in studio.memoryWarning() }
        }
    }
}
struct RootView: View {
    @AppStorage("tutorialSeen") private var tutorialSeen = false
    var body: some View {
        TabView {
            NavigationStack { HomeView() }.tabItem { Label("Home", systemImage: "house.fill") }
            NavigationStack { VoicesView() }.tabItem { Label("Voices", systemImage: "waveform") }
            NavigationStack { SavedView() }.tabItem { Label("Saved", systemImage: "folder.fill") }
            NavigationStack { HelpView() }.tabItem { Label("Help", systemImage: "questionmark.circle") }
            NavigationStack { SettingsView() }.tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .sheet(isPresented: Binding(get: { !tutorialSeen }, set: { tutorialSeen = !$0 })) {
            VStack(spacing: 26) {
                Image(systemName: "waveform.circle.fill").font(.system(size: 80)).foregroundStyle(.purple)
                Text("Welcome to VoiceMatrix").font(.largeTitle.bold())
                Text("1. Choose a voice\n2. Type a message\n3. Tap Speak\n4. Listen or Save").font(.title2).lineSpacing(12)
                Text("Your words and recordings stay on your iPhone. Included profiles are experimental; sound quality still needs listening tests.").foregroundStyle(.secondary)
                Button("LET’S START") { tutorialSeen = true }.buttonStyle(.borderedProminent).controlSize(.large)
            }.padding(28).presentationDetents([.large])
        }
    }
}
struct HomeView: View {
    @EnvironmentObject var studio: SpeechStudio
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Image(systemName: "waveform.circle.fill").font(.system(size: 62)).foregroundStyle(.purple, .blue)
                Text("Your voice.\nA new dimension.").font(.largeTitle.bold())
                Text("A private voice studio. No account needed.").foregroundStyle(.secondary)
                NavigationLink { SpeechView() } label: { HomeCard(title: "MAKE SPEECH", detail: "Type words. Choose a voice. Hear them speak.", icon: "text.bubble.fill") }.accessibilityIdentifier("make-speech")
                NavigationLink { RecordingView() } label: { HomeCard(title: "CHANGE MY VOICE", detail: "Record. Choose a voice. Hear your changed voice.", icon: "mic.fill") }.accessibilityIdentifier("change-my-voice")
                Text("\(studio.voices.count) bundled English profiles • Experimental\n\(studio.onDeviceSpeechChecks) speech checks completed on this iPhone.").font(.footnote).foregroundStyle(.secondary)
            }.padding(24)
        }.background(Color(red: 0.045, green: 0.025, blue: 0.09)).navigationTitle("VoiceMatrix")
    }
}
struct HomeCard: View {
    let title, detail, icon: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Image(systemName: icon).font(.largeTitle)
            Text(title).font(.title2.bold())
            Text(detail).font(.body)
        }.foregroundStyle(.white).frame(maxWidth: .infinity, minHeight: 140, alignment: .leading).padding(22)
            .background(LinearGradient(colors: [.purple.opacity(0.8), .indigo.opacity(0.7)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 26))
    }
}
struct SpeechView: View {
    @EnvironmentObject var studio: SpeechStudio
    @EnvironmentObject var audio: AudioStore
    @State private var words = "Hello! Welcome to your private voice studio."
    @State private var choosing = false
    @FocusState private var editingMessage: Bool
    var body: some View {
        ScrollViewReader { proxy in
        Form {
            Section("Step 1 · Choose a voice") {
                Button { choosing = true } label: { Label(studio.selected?.name ?? "Choose a voice", systemImage: "person.wave.2.fill") }.disabled(studio.busy)
                if let voice = studio.selected { Text(voice.description).font(.caption).foregroundStyle(.secondary) }
            }
            Section("Step 2 · Type your message") {
                TextEditor(text: $words).focused($editingMessage).frame(minHeight: 150).accessibilityLabel("Your message")
                Text("\(words.count) / 2,000 characters").font(.caption).foregroundStyle(words.count > 2000 ? .red : .secondary)
            }
            Section("Step 3 · Tap Speak") {
                Button { editingMessage = false; studio.speak(words, audio: audio) } label: { Label("SPEAK", systemImage: "play.fill").frame(maxWidth: .infinity, minHeight: 50).font(.title3.bold()) }.buttonStyle(.borderedProminent)
                    .disabled(studio.busy || studio.recordingInProgress || studio.selected == nil || words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || words.count > 2000)
                if studio.busy { ProgressView("Creating your speech…"); Button("Cancel", role: .cancel) { studio.cancel() } }
                Text(studio.status).font(.callout).accessibilityAddTraits(.updatesFrequently)
            }
            Section("Step 4 · Listen or Save") {
                if let url = studio.output { AudioActions(url: url) } else { Text("Your speech will appear here.").foregroundStyle(.secondary) }
            }.id("speech-result")
        }.onChange(of: studio.output) { _, value in
            if value != nil { withAnimation { proxy.scrollTo("speech-result", anchor: .bottom) } }
        }
        }.navigationTitle("Make Speech").sheet(isPresented: $choosing) { NavigationStack { VoicesView(onChoose: { choosing = false }) } }
    }
}
struct AudioActions: View {
    @EnvironmentObject var audio: AudioStore
    let url: URL
    var body: some View {
        Group {
        Button { audio.play(url) } label: { Label("Listen / Replay", systemImage: "play.fill") }
        if audio.playing != nil { Button("Stop") { audio.stop() } }
        Button { audio.save(url) } label: { Label(audio.isSaved(url) ? "Saved" : "Save Recording", systemImage: "square.and.arrow.down") }
            .disabled(audio.isSaved(url)).accessibilityIdentifier("save-recording")
        ShareLink(item: url) { Label("Share Audio", systemImage: "square.and.arrow.up") }
        if let error = audio.error { Text(error).foregroundStyle(.orange) }
        }.disabled(audio.microphoneInUse)
    }
}
struct VoicesView: View {
    @EnvironmentObject var studio: SpeechStudio
    @EnvironmentObject var audio: AudioStore
    var onChoose: (() -> Void)? = nil
    @State private var search = ""
    @State private var filter = "All"
    var filtered: [VoiceProfile] {
        studio.voices.filter { voice in
            (search.isEmpty || voice.searchText.localizedCaseInsensitiveContains(search)) &&
            (filter == "All" || (filter == "Favorites" && studio.favorites.contains(voice.id)) || (filter == "Recent" && studio.recent.contains(voice.id)) || (filter == "American" && voice.accent == "American") || voice.matchesCategory(filter))
        }
    }
    var body: some View {
        List {
            Section {
                Picker("Show", selection: $filter) {
                    ForEach(["All", "American", "Favorites", "Recent"] + Array(Set(studio.voices.flatMap(\.allCategories))).sorted(), id: \.self) { Text($0).tag($0) }
                }
                Text("Included experimental profiles. No celebrity likenesses or near-indistinguishable quality claims.").font(.caption).foregroundStyle(.secondary)
            }
            if filtered.isEmpty { Text("No matching voices. Try another search or filter.").foregroundStyle(.secondary) }
            ForEach(filtered) { voice in
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Button {
                            studio.selectedID = voice.id; onChoose?()
                        } label: {
                            HStack { Image(systemName: studio.selectedID == voice.id ? "checkmark.circle.fill" : "circle"); Text(voice.name).font(.headline) }
                        }.disabled(studio.busy).accessibilityLabel("Choose \(voice.name)").accessibilityValue(studio.selectedID == voice.id ? "Selected" : "Not selected").accessibilityIdentifier("voice-" + voice.id)
                        Spacer()
                        Button { studio.favorite(voice.id) } label: { Image(systemName: studio.favorites.contains(voice.id) ? "heart.fill" : "heart") }.accessibilityLabel("Favorite \(voice.name)")
                    }
                    Text(voice.description).font(.caption).foregroundStyle(.secondary)
                    Button {
                        studio.selectedID = voice.id
                        studio.speak("Hello! This is \(voice.name). Let’s bring your words to life.", audio: audio)
                    } label: { Label("Preview Voice", systemImage: "play.circle") }.disabled(studio.busy || studio.recordingInProgress)
                }.buttonStyle(.borderless).padding(.vertical, 6)
            }
            if studio.busy { ProgressView("Creating preview…"); Button("Cancel Preview") { studio.cancel() } }
            Text(studio.status).font(.footnote)
        }.searchable(text: $search, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search voices or styles").navigationTitle("Voices")
    }
}
struct SavedView: View {
    @EnvironmentObject var audio: AudioStore
    @State private var editing: SavedAudio?
    @State private var newName = ""
    var body: some View {
        List {
            if audio.recordings.isEmpty { ContentUnavailableView("No recordings yet", systemImage: "waveform", description: Text("Make speech or record audio, then tap Save.")) }
            ForEach(audio.recordings) { file in
                DisclosureGroup(file.name) {
                    Button("Listen") { audio.play(file.url) }
                    ShareLink(item: file.url) { Label("Share", systemImage: "square.and.arrow.up") }
                    Button("Rename") { newName = file.name; editing = file }
                    Button("Delete", role: .destructive) { audio.delete(file) }
                }
            }
            if audio.playing != nil { Button("Stop Playback") { audio.stop() } }
            if let error = audio.error { Text(error).foregroundStyle(.orange) }
        }.navigationTitle("Saved Recordings").onAppear { audio.refresh() }
            .alert("Rename recording", isPresented: Binding(get: { editing != nil }, set: { if !$0 { editing = nil } })) {
                TextField("Name", text: $newName)
                Button("Save") { if let editing { audio.rename(editing, to: newName) }; editing = nil }
                Button("Cancel", role: .cancel) { editing = nil }
            }
    }
}
struct HelpView: View {
    var body: some View {
        Form {
            Section("Make speech") { Text("Choose Make Speech, select a voice, type your message, then tap Speak. Raise your iPhone volume if you cannot hear it. Tap Save to keep the WAV in Saved Recordings.") }
            Section("Recording") { Text("Allow microphone access when asked. If it was denied, open iPhone Settings and enable the microphone for VoiceMatrix or your LiveContainer / Strata host. Recordings remain private unless you tap Share.") }
            Section("Voice changing") { Text("Record or import up to 10 seconds of clear speech, choose a voice, and tap Convert. This uses the included offline voice-changing model. Your words and timing are preserved as closely as the model permits; this is not live voice changing.") }
            Section("Troubleshooting") { Text("If a voice cannot start, try another voice. If the included files are missing or damaged, reinstall the complete build. No model downloads happen inside this app. Reports in Settings exclude your messages and recordings.") }
        }.navigationTitle("Help")
    }
}
struct SettingsView: View {
    @EnvironmentObject var studio: SpeechStudio
    @EnvironmentObject var audio: AudioStore
    @State private var report: URL?
    var body: some View {
        Form {
            Section("VoiceMatrix \(DeviceVoiceChecks.appVersion) · Experimental") {
                Text("\(studio.voices.count) bundled English profiles\n\(studio.automatedChecks) automated speech checks passed (simulator)\n\(studio.onDeviceSpeechChecks) speech checks completed on this iPhone\n0 authorized recognizable likenesses\nQuality listening tests pending")
                Text("All speech and voice-changing files are included. No account or model download is needed.")
                Text("Profile storage: \(ByteCountFormatter.string(fromByteCount: Int64(studio.voices.reduce(0) { $0 + $1.size }), countStyle: .file))")
            }
            Section("Check included voices") {
                Button("CHECK ALL VOICES") { studio.checkIncludedVoices(audio: audio) }.disabled(studio.busy || studio.recordingInProgress)
                if studio.checkingVoices {
                    ProgressView(value: studio.checkProgress)
                    Button("Stop Checks") { studio.cancel() }
                }
                Text("Tests every included voice without saving recordings. Keep the app open. These audio checks do not replace listening comparisons.").font(.caption)
                Text(studio.status).font(.caption)
            }
            Section("Listening speed") {
                Slider(value: Binding(get: { audio.rate }, set: { audio.rate = $0 }), in: 0.7...1.3)
                Text("Applies the next time you tap Listen. Saved audio keeps its original speed.").font(.caption)
            }
            Section("Error report") {
                Button("Prepare Private Error Report") { report = studio.diagnosticFile() }
                if let report { ShareLink(item: report) { Label("Share Error Report", systemImage: "square.and.arrow.up") } }
                Text("Nothing is uploaded automatically. Reports contain engine events and profile IDs, without entered text or audio.").font(.caption)
            }
            Section("Licenses") { Text("FluidAudio and Phonon: Apache 2.0. OpenVoice V2: MIT. Reference voices use CC0, CC BY 4.0, or CC BY-NC 4.0 as marked. Some voices are for noncommercial use only. Full notices and source records are bundled. No official character or performer endorsement is claimed.") }
        }.navigationTitle("Settings")
    }
}
