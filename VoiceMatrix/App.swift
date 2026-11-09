import SwiftUI
import AVFoundation

@main struct VoiceMatrixApp: App {
    init() { TemporaryAudio.cleanPreviousSession() }
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var studio = SpeechStudio()
    @StateObject private var audio = AudioStore()
    @StateObject private var characters = CharacterLibrary()
    var body: some Scene {
        WindowGroup { RootView().environmentObject(studio).environmentObject(audio).environmentObject(characters).preferredColorScheme(.dark).tint(StudioPalette.accent)
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didReceiveMemoryWarningNotification)) { _ in studio.memoryWarning(); characters.releaseWarmSpeech() }
            .onChange(of: scenePhase, initial: true) { _, phase in characters.setApplicationActive(phase == .active) }
            .onChange(of: studio.busy) { _, busy in if busy { characters.releaseWarmSpeech() } }
        }
    }
}
struct RootView: View {
    @EnvironmentObject var studio: SpeechStudio
    @State private var clearedInitialSelection = false
    @AppStorage("tutorialSeen") private var tutorialSeen = false
    var body: some View {
        TabView {
            NavigationStack { HomeView() }.tabItem { Label("Home", systemImage: "house.fill") }
            NavigationStack { CharacterLibraryView() }.tabItem { Label("Voices", systemImage: "waveform") }
            NavigationStack { SavedView() }.tabItem { Label("Saved", systemImage: "folder.fill") }
            NavigationStack { HelpView() }.tabItem { Label("Help", systemImage: "questionmark.circle") }
            NavigationStack { SettingsView() }.tabItem { Label("Settings", systemImage: "gearshape") }
        }
        .onAppear { if !clearedInitialSelection { studio.selectedID = ""; clearedInitialSelection = true } }
        .sheet(isPresented: Binding(get: { !tutorialSeen }, set: { tutorialSeen = !$0 })) {
            VStack(spacing: 26) {
                Image(systemName: "waveform.circle.fill").font(.system(size: 80)).foregroundStyle(.purple)
                Text("Welcome to VoiceMatrix").font(.largeTitle.bold())
                Text("1. Choose your Voices folder\n2. Choose a character\n3. Type or record your words\n4. Listen, Save or Share").font(.title2).lineSpacing(12)
                Text("Speech and voice changing run on your iPhone. Your separate references are experimental; compare each character before approving its sound.").foregroundStyle(.secondary)
                Button("LET’S START") { tutorialSeen = true }.buttonStyle(.borderedProminent).controlSize(.large)
            }.padding(28).presentationDetents([.large])
        }
    }
}
enum StudioPalette {
    static let background = Color(red: 0.035, green: 0.04, blue: 0.075)
    static let surface = Color(red: 0.085, green: 0.09, blue: 0.14)
    static let accent = Color(red: 0.68, green: 0.53, blue: 1)
    static let mint = Color(red: 0.35, green: 0.85, blue: 0.77)
}
struct HomeView: View {
    @EnvironmentObject var library: CharacterLibrary
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack {
                    Label("YOUR PRIVATE STUDIO", systemImage: "waveform")
                        .font(.caption.weight(.bold)).tracking(2).foregroundStyle(StudioPalette.mint)
                    Spacer()
                }
                Text("Give your words\na new voice.")
                    .font(.system(.largeTitle, design: .rounded, weight: .bold))
                Text("Pick a character. Create something worth hearing.")
                    .foregroundStyle(.secondary)
                VStack(spacing: 12) {
                    NavigationLink { CharacterLibraryView() } label: {
                        HomeCard(title: "Make speech", detail: "Type a message. Bring it to life.", icon: "text.bubble.fill", prominent: true)
                    }.accessibilityIdentifier("make-speech")
                    NavigationLink { CharacterLibraryView(mode: .conversion) } label: {
                        HomeCard(title: "Change my voice", detail: "Record or import your own words.", icon: "mic.fill")
                    }.accessibilityIdentifier("change-my-voice")
                }
                VStack(alignment: .leading, spacing: 14) {
                    Text("Your collection").font(.title3.bold())
                    NavigationLink { CharacterLibraryView() } label: {
                        HStack(spacing: 14) {
                            Image(systemName: "person.2.wave.2.fill").font(.title2).foregroundStyle(StudioPalette.mint)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(library.profiles.isEmpty ? "Add your voices" : "\(library.profiles.count) voices on this iPhone").font(.headline)
                                Text("Browse, import or sync your collection").font(.subheadline).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption.bold())
                        }.padding(20).background(StudioPalette.surface, in: RoundedRectangle(cornerRadius: 22))
                    }
                    NavigationLink { VideoQueueView() } label: {
                        Label("Video requests", systemImage: "list.bullet.rectangle").font(.subheadline.weight(.semibold))
                    }.padding(.vertical, 8)
                }
                Label("Your saved voices work offline", systemImage: "lock.shield")
                    .font(.footnote).foregroundStyle(.secondary)
            }.padding(24)
        }
        .background(StudioPalette.background).navigationTitle("VoiceMatrix")
        .task { await library.loadAndRefresh() }
    }
}
struct HomeCard: View {
    let title, detail, icon: String
    var prominent = false
    var body: some View {
        HStack(spacing: 18) {
            Image(systemName: icon).font(.title2)
                .frame(width: 52, height: 52)
                .background(.white.opacity(0.12), in: RoundedRectangle(cornerRadius: 16))
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.title3.bold())
                Text(detail).font(.subheadline).foregroundStyle(.white.opacity(0.8))
            }
            Spacer(minLength: 0)
            Image(systemName: "arrow.up.right").font(.headline)
        }
        .foregroundStyle(.white).padding(20).frame(maxWidth: .infinity, alignment: .leading)
        .background(LinearGradient(colors: prominent ? [Color(red: 0.38, green: 0.23, blue: 0.7), Color(red: 0.24, green: 0.19, blue: 0.46)] : [StudioPalette.surface, StudioPalette.surface], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 24))
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
    @State private var library = "Replicas"
    var filtered: [VoiceProfile] {
        studio.voices.filter { voice in
            (library == "All voices" || voice.libraryGroup == library) &&
            (search.isEmpty || voice.searchText.localizedCaseInsensitiveContains(search)) &&
            (filter == "All" || (filter == "Favorites" && studio.favorites.contains(voice.id)) || (filter == "Recent" && studio.recent.contains(voice.id)) || (filter == "American" && voice.accent == "American") || voice.matchesCategory(filter))
        }
    }
    var body: some View {
        List {
            Section {
                Picker("Voice library", selection: $library) {
                    ForEach(["Character styles", "Replicas", "Other speakers", "All voices"], id: \.self) { Text($0 == "Replicas" ? "Your characters" : $0 == "Character styles" ? "Optional original styles" : $0 == "Other speakers" ? "Optional general speakers" : "All optional voices").tag($0) }
                }.accessibilityIdentifier("voice-library")
                Text("\(studio.voices.filter { $0.libraryGroup == "Replicas" }.count) replica entries • \(studio.voices.filter { $0.libraryGroup == "Character styles" }.count) original character styles")
                    .font(.caption).foregroundStyle(.secondary)
                Picker("Show", selection: $filter) {
                    ForEach(["All", "American", "Favorites", "Recent"] + Array(Set(studio.voices.flatMap(\.allCategories))).sorted(), id: \.self) { Text($0).tag($0) }
                }
                Text("Replicas require a named target and authorization records. Original character styles and other speakers are separate. Character resemblance still requires listening comparisons.").font(.caption).foregroundStyle(.secondary)
            }
            if filtered.isEmpty { Text(library == "Replicas" ? "Your character voices are not ready to use on this iPhone yet. The Rick and Morty samples you approved are preserved as previews. Adding a video request does not install a reusable voice." : "No matching voices. Try another search or filter.").foregroundStyle(.secondary) }
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
                    Text(voice.identityLabel).font(.caption).foregroundStyle(.purple)
                    Text(voice.description).font(.caption).foregroundStyle(.secondary)
                    Button {
                        studio.selectedID = voice.id
                        studio.speak("Hello! This is \(voice.name). Let’s bring your words to life.", audio: audio)
                    } label: { Label("Preview Voice", systemImage: "play.circle") }.disabled(studio.busy || studio.recordingInProgress)
                }.buttonStyle(.borderless).padding(.vertical, 6)
            }
            if studio.busy { ProgressView("Creating preview…"); Button("Cancel Preview") { studio.cancel() } }
            Text(filtered.isEmpty ? "No voice is selected. Add a video request from Home → Video List while your character voices are being prepared." : studio.status).font(.footnote)
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
    @EnvironmentObject var library: CharacterLibrary
    @State private var report: URL?
    var body: some View {
        Form {
            Section("VoiceMatrix \(DeviceVoiceChecks.appVersion)") {
                Label("\(library.profiles.count) imported voices", systemImage: "person.2.wave.2")
                Text("Your collection and saved recordings stay on this iPhone. Speech and voice changing run locally.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }
            Section("App updates") {
                NavigationLink("Check for Updates") { AppUpdatesView() }.accessibilityIdentifier("app-updates")
            }
            Section("Listening speed") {
                Slider(value: Binding(get: { audio.rate }, set: { audio.rate = $0 }), in: 0.7...1.3)
                Text("Applies the next time you tap Listen. Saved audio keeps its original speed.").font(.caption)
            }
            Section("Suggestions") { NavigationLink("Send a suggestion") { SuggestionsView() } }
            Section("Error report") {
                Button("Prepare Private Error Report") { report = studio.diagnosticFile() }
                if let report { ShareLink(item: report) { Label("Share Error Report", systemImage: "square.and.arrow.up") } }
                Text("Nothing is uploaded automatically. Reports contain engine events and profile IDs, without entered text or audio.").font(.caption)
            }
            Section("Licenses") { Text("Full engine licenses and notices are included in the app. F5 weights carry noncommercial terms. Imported references retain their own permission records. No official character or performer endorsement is claimed.") }
        }.navigationTitle("Settings")
    }
}
