import SwiftUI
import UniformTypeIdentifiers

struct LocalVideoStudioView: View {
    @EnvironmentObject private var local: LocalVideoStudio
    @EnvironmentObject private var library: CharacterLibrary
    @EnvironmentObject private var audio: AudioStore
    @EnvironmentObject private var speech: SpeechStudio
    @State private var importing = false
    @State private var selected: URL?
    @State private var authorized = false
    @State private var selectionError: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("On this iPhone").font(.title2.bold())
                Text("Import a local video or recording. Extraction, English transcription, reference-conditioned preview and voice registration run inside this app. No laptop or server fallback.")
                Text("Bundled analysis groups speakers and excludes detected overlap. Local sound screening rejects likely music, singing or insufficient speech. It does not identify characters, remove music or train RVC models. Every accepted reference must pass a word check; resemblance needs listening review.").font(.footnote).foregroundStyle(.secondary)
                Button(selected == nil ? "Choose video or audio" : "Choose a different file") { importing = true }
                    .buttonStyle(.bordered).disabled(local.busy).accessibilityIdentifier("local-video-import")
                if selected != nil { Label("Local media selected", systemImage: "doc.fill") }
                Toggle("I am authorized to use this media and its voices", isOn: $authorized).disabled(local.busy)
                Button("Generate speaker references") {
                    if let selected { local.start(selected, authorized: authorized, library: library, audio: audio, speech: speech) }
                }.buttonStyle(.borderedProminent).disabled(selected == nil || !authorized || local.busy)
                    .accessibilityIdentifier("local-video-generate")
                if let selectionError { Text(selectionError).foregroundStyle(.red) }
                Text(local.notice).accessibilityIdentifier("local-video-status")
                if local.busy {
                    ProgressView("Working on this iPhone…")
                    Button("Pause and retain files") { local.cancel() }.buttonStyle(.bordered)
                } else if let job = local.current, !job.completed, job.sourceFile != nil {
                    Button("Resume retained job") { local.resume(library: library, audio: audio, speech: speech) }.buttonStyle(.bordered)
                }
                if let reference = local.reference { Button("Listen to reference") { audio.play(reference) }.disabled(local.busy) }
                if let preview = local.preview { Button("Listen to generated preview") { audio.play(preview) }.disabled(local.busy) }
                if local.current?.voiceID != nil {
                    NavigationLink("Use saved references for new speech") { CharacterLibraryView() }
                }
                if let outcomes = local.current?.speakerOutcomes, !outcomes.isEmpty {
                    Text("Speaker results").font(.headline)
                    ForEach(outcomes.keys.sorted(), id: \.self) { speaker in
                        Text("Unidentified speaker \(speaker): \(outcomes[speaker] ?? "Pending")").font(.caption)
                    }
                }
                Divider()
                Text("Live processing log").font(.headline)
                TimelineView(.periodic(from: .now, by: 1)) { timeline in
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Log view refreshed " + timeline.date.formatted(date: .omitted, time: .standard)).font(.caption)
                        if let job = local.current {
                            Text((local.busy ? "Stage: " : "Not running · last retained stage: ") + job.stage).font(.headline)
                            Text("Last actual update: " + job.updated.formatted(date: .omitted, time: .standard)).font(.caption)
                            if local.busy, timeline.date.timeIntervalSince(job.updated) >= 30 {
                                Text("No new stage activity for \(Int(timeline.date.timeIntervalSince(job.updated))) seconds. The current operation may still be busy; this is not a failure declaration.").foregroundStyle(.orange)
                            }
                            ForEach(Array(job.events.reversed())) { event in
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(event.time.formatted(date: .omitted, time: .standard) + " · " + event.stage).font(.caption.bold())
                                    Text(event.message).font(.caption)
                                }.frame(maxWidth: .infinity, alignment: .leading)
                            }
                        } else { Text("No local job has started.").font(.caption) }
                    }
                }.accessibilityIdentifier("local-video-live-log")
                Text("Keep VoiceMatrix open while processing. Leaving the app pauses at a safe boundary. Files remain available for Resume; iOS does not guarantee unlimited background processing.").font(.footnote).foregroundStyle(.secondary)
                if !local.history.isEmpty {
                    Divider(); Text("Retained job history").font(.headline)
                    ForEach(local.history) { job in
                        Button { local.selectHistory(job) } label: {
                            VStack(alignment: .leading) {
                                Text(job.created.formatted(date: .abbreviated, time: .shortened))
                                Text(job.stage).font(.caption)
                            }
                        }.disabled(local.busy)
                    }
                }
            }.padding(20)
        }
        .navigationTitle("Video Voice Studio")
        .fileImporter(isPresented: $importing, allowedContentTypes: [.movie, .audio]) { result in
            switch result {
            case .success(let url): selected = url; authorized = false; selectionError = nil
            case .failure: selectionError = "The selected file could not be opened. No job was started."
            }
        }
    }
}
