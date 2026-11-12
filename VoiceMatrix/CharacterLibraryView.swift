import SwiftUI
import UniformTypeIdentifiers
import CryptoKit

enum CharacterStudioMode: String, CaseIterable { case speech, conversion }

struct CharacterLibraryView: View {
    @State private var mode: CharacterStudioMode
    @StateObject private var recorder = Recorder()
    private enum ImportKind { case folder, audio }
    @State private var importKind: ImportKind = .folder
    @State private var showingImporter = false
    @State private var choosingVoice = false
    @State private var showingSyncLog = false
    @FocusState private var editingWords: Bool
    init(mode: CharacterStudioMode = .speech) { _mode = State(initialValue: mode) }
    @EnvironmentObject private var library: CharacterLibrary
    @Environment(\.scenePhase) private var scenePhase
    @EnvironmentObject private var audio: AudioStore
    @EnvironmentObject private var studio: SpeechStudio
    @State private var controls = SpeechControls()
    @State private var words = "Hello! Welcome to the character voice studio."
    var body: some View {
        List {
            Section {
                Button { choosingVoice = true } label: {
                    HStack(spacing: 14) {
                        Image(systemName: "person.wave.2.fill").font(.title2)
                            .foregroundStyle(StudioPalette.mint)
                        VStack(alignment: .leading, spacing: 5) {
                            Text("YOUR VOICE").font(.caption.weight(.bold)).tracking(1.5).foregroundStyle(.secondary)
                            Text(library.profiles.first(where: { $0.id == library.selectedID })?.name ?? "Choose a character")
                                .font(.title3.bold()).foregroundStyle(.primary)
                            Text(library.availableProfiles.isEmpty ? "Browse the laptop catalog to get started" : "Browse \(library.availableProfiles.count) voices · \(library.profiles.count) downloaded")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: "chevron.down").font(.caption.bold())
                    }.padding(.vertical, 8)
                }.disabled(library.busy || recorder.recording).accessibilityIdentifier("choose-character")
                if library.selectedID.isEmpty {
                    Text("Choose a voice first, then type or record your words.")
                        .font(.subheadline).foregroundStyle(.secondary)
                        .accessibilityIdentifier("character-selection-guidance")
                }
            }
            Section {
                DisclosureGroup("Manage your collection") {
                    Button { library.syncVoices() } label: { Label("Refresh laptop catalog", systemImage: "arrow.triangle.2.circlepath") }
                        .disabled(library.busy || library.syncing || !LaptopConnection.paired)
                    if library.syncing { ProgressView(library.downloadingID == nil ? "Refreshing catalog…" : "Downloading voice…"); Button("Stop sync", role: .cancel) { library.cancelSync() }.disabled(!library.syncCanStop) }
                    Button { showingSyncLog = true } label: { Label("Live sync log", systemImage: "list.bullet.rectangle") }
                        .accessibilityIdentifier("live-sync-log")
                    if let latest = library.syncEvents.last { Text(latest.progress.message).font(.caption).foregroundStyle(.secondary) }
                    Button { importKind = .folder; showingImporter = true } label: { Label("Choose Voices Folder", systemImage: "folder.badge.plus") }
                        .disabled(library.busy || library.downloadingID != nil).accessibilityIdentifier("import-character-folder")
                    Text(library.catalogStatus).font(.caption).foregroundStyle(.secondary)
                    if let bytes = library.storedVoiceBytes {
                        Text("Saved voice files: " + ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Text("Refresh checks names and availability only. Download individual voices in the picker while online; downloaded and imported voices stay on this iPhone. The app refreshes when opened, not continuously in the background.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
            Section {
                Picker("What would you like to do?", selection: $mode) {
                    Text("Make Speech").tag(CharacterStudioMode.speech)
                    Text("Change My Voice").tag(CharacterStudioMode.conversion)
                }.pickerStyle(.segmented).disabled(library.busy || recorder.recording)
            }
            if mode == .speech {
            Section("Make character speech") {
                Text(library.profiles.first(where: { $0.id == library.selectedID })?.name ?? "Choose an imported character above")
                TextEditor(text: $words).focused($editingWords).frame(minHeight: 140).accessibilityLabel("Words for your character")
                Text("\(words.count) characters · split into complete-word parts").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Text("No fixed character cap. Jobs are limited to about 30 minutes before speed changes; longer text must be split. Keep the app open. Long jobs use battery and storage.")
                    .font(.caption).foregroundStyle(.secondary)
                DisclosureGroup("Speech controls") {
                    Text(String(format: "Speed · %.2fx", controls.speed))
                    Slider(value: $controls.speed, in: 0.5...2, step: 0.05).accessibilityLabel("Speech speed")
                    Text(String(format: "Pitch · %+.0f semitones", controls.pitch))
                    Slider(value: $controls.pitch, in: -12...12, step: 1).accessibilityLabel("Speech pitch")
                    Text(String(format: "Volume · %.0f%%", controls.volume * 100))
                    Slider(value: $controls.volume, in: 0.25...1, step: 0.05).accessibilityLabel("Speech volume")
                    Text(String(format: "Pause between generated parts · %.2f seconds", controls.pause))
                    Slider(value: $controls.pause, in: 0...1, step: 0.05).accessibilityLabel("Speech part pause")
                    Button("Reset speech controls") { controls = SpeechControls() }.accessibilityIdentifier("reset-speech-controls")
                    Text("Applied when you create speech, including saved/shared audio. Pitch shifts may change resemblance. Reference recordings are unchanged.")
                        .font(.caption).foregroundStyle(.secondary)
                }.disabled(library.busy)

                Button { editingWords = false; audio.stop(); library.speak(words, audio: audio, studio: studio, controls: controls) } label: { Label("Create speech", systemImage: "waveform").font(.headline).frame(maxWidth: .infinity, minHeight: 48) }
                    .buttonStyle(.borderedProminent).accessibilityIdentifier("create-character-speech")
                    .disabled(library.busy || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse || !library.engineAvailable || words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                if library.busy { ProgressView(library.message); Button("Stop after current step", role: .cancel) { library.cancel() } }
                Text(library.message).font(.caption).foregroundStyle(.secondary).accessibilityAddTraits(.updatesFrequently)
                if !library.engineAvailable { Text("The shared F5 engine is absent from this build. Your imported voice samples remain saved; speech testing becomes available in a build containing that engine.").foregroundStyle(.secondary) }
                Text("Creates new words using your selected voice.").font(.caption).foregroundStyle(.secondary)
                if let output = library.output, library.outputKind == "speech", library.outputMatchesSelection {
                    Text("Created with " + library.outputSettings).font(.caption).foregroundStyle(.secondary)
                    AudioActions(url: output)
                }
                else { Text("Create speech with this character to listen or save.").foregroundStyle(.secondary) }
            }
            } else {
                Section("1 · Record your words") {
                    Button {
                        if recorder.recording { recorder.stop() } else { Task { await recorder.start(audio: audio) } }
                    } label: { Label(recorder.recording ? "STOP RECORDING" : "RECORD MY VOICE", systemImage: recorder.recording ? "stop.fill" : "mic.fill").frame(minHeight: 52) }
                        .buttonStyle(.borderedProminent).disabled(library.busy || recorder.requestingPermission || (audio.processingInUse && !recorder.recording))
                    Button("Import Audio") { importKind = .audio; showingImporter = true }.disabled(library.busy || recorder.recording || recorder.requestingPermission)
                    Text(recorder.status)
                    Text("Use up to 10 seconds of clear speech. Your words and timing are processed locally.").font(.caption).foregroundStyle(.secondary)
                }
                Section("2 · Choose a character above, then Convert") {
                    Text(library.profiles.first(where: { $0.id == library.selectedID })?.name ?? "Choose a character above")
                    Button {
                        if let source = recorder.output { library.convertRecording(source, audio: audio, studio: studio) }
                    } label: { Label("CONVERT", systemImage: "waveform").frame(minHeight: 52) }.buttonStyle(.borderedProminent)
                        .disabled(library.busy || recorder.recording || recorder.requestingPermission || recorder.output == nil || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse || !library.conversionAvailable)
                if library.busy { ProgressView(library.message); Button("Stop after current step", role: .cancel) { library.cancel() } }
                    Text(library.message).font(.caption).foregroundStyle(.secondary).accessibilityAddTraits(.updatesFrequently)
                    if !library.conversionAvailable { Text("This build needs the shared voice-changing engine before conversion can run.").foregroundStyle(.secondary) }
                    if let source = recorder.output, !recorder.recording { Button("Listen to my original recording") { audio.play(source) }.disabled(library.busy) }
                    Text("Changes a recording on your iPhone. Not for live calls.").font(.caption).foregroundStyle(.secondary)
                    if let output = library.output, library.outputKind == "conversion", library.outputMatchesSelection { AudioActions(url: output) }
                }
            }
            Section { NavigationLink("Send a suggestion") { SuggestionsView() } }
            Section("Playback & comparison") {
                Text("Compare the original voice with your new audio.").font(.subheadline).foregroundStyle(.secondary)
                if let selected = library.profiles.first(where: { $0.id == library.selectedID }) {
                    Text("Selected: " + selected.name)
                } else {
                    Text("Choose a character at the top to hear its reference.")
                }
                Button { library.listenToReference(audio: audio) } label: { Label("1 · Listen to reference", systemImage: "person.wave.2") }
                    .disabled(library.busy || library.selectedID.isEmpty || audio.microphoneInUse || audio.processingInUse)
                TimelineView(.periodic(from: .now, by: 0.5)) { _ in
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Output: " + audio.outputRoute + " · Volume: " + String(audio.outputVolumePercent) + "%")
                            .font(.caption)
                        if audio.playing != nil {
                            Text(String(format: "Playing · %.1f / %.1f seconds", audio.elapsedSeconds, audio.durationSeconds))
                                .monospacedDigit().accessibilityIdentifier("character-playback-progress")
                        }
                    }
                }
                if audio.playing != nil {
                    Button("Stop playback") { audio.stop() }.accessibilityIdentifier("stop-character-playback")
                }
                if let error = audio.error {
                    Text(error).foregroundStyle(.orange).accessibilityIdentifier("character-playback-error")
                }
                if let output = library.output, library.canReview {
                    Button { audio.play(output) } label: { Label("2 · Listen to result", systemImage: "waveform") }
                    Button("Matches") { library.review(.matches) }.accessibilityIdentifier("character-match-yes")
                    Button("Doesn’t Match") { library.review(.different) }.accessibilityIdentifier("character-match-no")
                    Button("Unsure") { library.review(.unsure) }.accessibilityIdentifier("character-match-unsure")
                } else { Text("Create speech with the selected reference before reviewing it.").foregroundStyle(.secondary) }
                if let voice = library.profiles.first(where: { $0.id == library.selectedID }) { Text(library.matchDescription(voice)).font(.caption) }
            }
        }
        .navigationTitle(mode == .speech ? "Make Speech" : "Change My Voice")
        .scrollContentBackground(.hidden)
        .background(StudioPalette.background)
        .scrollDismissesKeyboard(.interactively)
        .toolbar { ToolbarItemGroup(placement: .keyboard) { Spacer(); Button("Done") { editingWords = false } } }
        .sheet(isPresented: $showingSyncLog) { NavigationStack { VoiceSyncLogView() } }
        .sheet(isPresented: $choosingVoice) { NavigationStack { CharacterPickerView() } }
        // One presenter avoids the audio importer masking the folder importer.
        .fileImporter(isPresented: $showingImporter,
                      allowedContentTypes: importKind == .folder ? [.folder] : [.wav, .mpeg4Audio, .audio]) { result in
            switch (importKind, result) {
            case (.folder, .success(let url)): library.importFolder(url)
            case (.folder, .failure(let error)): library.message = "The folder could not be opened. " + error.localizedDescription
            case (.audio, .success(let url)): recorder.importAudio(url)
            case (.audio, .failure): recorder.status = "That recording could not be opened. Try a WAV or M4A file."
            }
        }
        .onDisappear { recorder.discard(); audio.stop() }
        .task {
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-ui-test-import"),
               library.profiles.isEmpty,
               let fixture = Bundle.main.url(forResource: "F5TTS", withExtension: nil)?.appendingPathComponent("UITestVoices"),
               FileManager.default.fileExists(atPath: fixture.path) {
                do {
                    let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("UIImport-" + UUID().uuidString)
                    try FileManager.default.copyItem(at: fixture, to: temporary)
                    library.importFolder(temporary)
                    while library.busy { try await Task.sleep(for: .milliseconds(100)) }
                    // Make the original source unavailable before restart: only the
                    // private imported copy can satisfy the persistence/playback test.
                    try FileManager.default.removeItem(at: temporary)
                } catch { library.message = "UI fixture import failed: " + error.localizedDescription }
            } else { await library.loadAndRefresh() }
            #else
            await library.loadAndRefresh()
            #endif
        }
        .onChange(of: scenePhase) { _, value in if value == .active { Task { await library.loadAndRefresh() } } }
    }
}

struct CharacterPickerView: View {
    @EnvironmentObject private var library: CharacterLibrary
    @Environment(\.dismiss) private var dismiss
    @State private var search = ""
    @State private var category = "All"
    private var categories: [String] { ["All"] + Set(library.availableProfiles.flatMap(\.categories)).sorted() }
    private var filtered: [CharacterReference] {
        library.availableProfiles.filter {
            (category == "All" || $0.categories.contains(category)) &&
            (search.isEmpty || ([$0.name] + $0.categories).joined(separator: " ").localizedCaseInsensitiveContains(search))
        }
    }
    var body: some View {
        List {
            Section {
                Picker("Category", selection: $category) {
                    ForEach(categories, id: \.self) { Text($0).tag($0) }
                }
                Text("\(filtered.count) voices · \(library.profiles.count) downloaded").font(.caption).foregroundStyle(.secondary)
                Text(library.catalogStatus).font(.caption).foregroundStyle(.secondary)
                Button("Refresh laptop catalog") { library.syncVoices() }
                    .disabled(library.busy || library.syncing || !LaptopConnection.paired)
                if library.syncing {
                    ProgressView(library.downloadingID == nil ? "Refreshing catalog…" : "Downloading voice…")
                    Button("Stop sync", role: .cancel) { library.cancelSync() }.disabled(!library.syncCanStop)
                }
                Text(library.message).font(.caption).foregroundStyle(.secondary)
                Text("Online required for new downloads. Downloaded voices work without the laptop.").font(.caption).foregroundStyle(.secondary)
            }
            if filtered.isEmpty {
                ContentUnavailableView(library.availableProfiles.isEmpty ? "Browse your voices" : "No matching voices",
                    systemImage: "person.2.wave.2",
                    description: Text(library.availableProfiles.isEmpty ? "Connect through Tailscale and refresh the laptop catalog, or import your Voices folder." : "Try a different name or category."))
            }
            ForEach(filtered) { voice in
                VStack(alignment: .leading, spacing: 8) {
                    Button {
                        library.selectedID = voice.id
                        dismiss()
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: library.selectedID == voice.id ? "checkmark.circle.fill" : "person.crop.circle")
                                .font(.title2).foregroundStyle(StudioPalette.mint)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(voice.name).font(.headline).foregroundStyle(.primary)
                                Text(voice.categories.joined(separator: " · ")).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                        }.padding(.vertical, 8)
                    }.buttonStyle(.plain).disabled(library.busy || !library.isDownloaded(voice.id))
                        .accessibilityIdentifier("select-character-" + voice.id)
                        .accessibilityValue(library.selectedID == voice.id ? "Selected" : "Not selected")
                    if library.isDownloaded(voice.id) {
                        Label("Downloaded · ready offline", systemImage: "checkmark.circle.fill").font(.caption).foregroundStyle(StudioPalette.mint)
                        if library.hasChangedRemoteReference(voice) {
                            Text("The laptop has a changed reference. Your saved version is kept until a reviewed replacement is supported.").font(.caption).foregroundStyle(.secondary)
                        }
                    } else {
                        Button { library.downloadVoice(voice) } label: { Label("Download for offline · " + library.downloadSize(voice.id), systemImage: "arrow.down.circle") }
                            .disabled(library.busy || library.syncing || !LaptopConnection.paired)
                            .accessibilityIdentifier("download-character-" + voice.id)
                        Text("Online required · available on laptop").font(.caption).foregroundStyle(.secondary)
                    }
                    DisclosureGroup("Voice details") {
                        Text("Source: " + voice.source)
                        Text("Permission record: " + voice.permission)
                        Text(library.matchDescription(voice)).font(.caption)
                    }.font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .task { await library.loadAndRefresh() }
        .navigationTitle("Choose a voice")
        .searchable(text: $search, prompt: "Search names or categories")
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        .scrollContentBackground(.hidden).background(StudioPalette.background)
    }
}


private struct VoiceSyncLogView: View {
    @EnvironmentObject private var library: CharacterLibrary
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        List {
            Section {
                if library.syncing, let started = library.syncStarted {
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        Text("Sync running · \(Int(context.date.timeIntervalSince(started))) seconds elapsed")
                        if let last = library.syncEvents.last {
                            Text("Last activity \(max(0, Int(context.date.timeIntervalSince(last.date)))) seconds ago. Waiting is not proof of progress.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Button("Stop sync", role: .cancel) { library.cancelSync() }.disabled(!library.syncCanStop)
                } else {
                    Button("Refresh laptop catalog") { library.syncVoices() }
                        .disabled(library.busy || !LaptopConnection.paired)
                }
                Text("Laptop entries are based on received responses. iPhone entries show download, validation and saving. No voice names, recordings or transcripts are logged.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Latest activity first") {
                if library.syncEvents.isEmpty { Text("No sync activity in this app session yet.") }
                ForEach(library.syncEvents.reversed()) { event in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(event.progress.message)
                        Text("\(event.date.formatted(date: .omitted, time: .standard)) · \(event.progress.source)")
                            .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }
                }
            }
        }
        .navigationTitle("Live sync log")
        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
    }
}
