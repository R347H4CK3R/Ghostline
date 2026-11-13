import UIKit
import SwiftUI
import UniformTypeIdentifiers

struct LocalVideoStudioView: View {
    @EnvironmentObject private var local: LocalVideoStudio
    @EnvironmentObject private var library: CharacterLibrary
    @EnvironmentObject private var audio: AudioStore
    @EnvironmentObject private var speech: SpeechStudio
    @State private var journalPage: LocalStudioJournal.Page?
    @State private var journalError: String?
    @State private var sourceURL = ""
    @State private var importing = false
    @State private var selected: URL?
    @State private var authorized = false
    @State private var selectionError: String?
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("On this iPhone").font(.title2.bold())
                Text("Import a local video or recording, or acquire supported public website media directly. Extraction, English transcription, reference-conditioned preview and voice registration run inside this app. No laptop or server fallback.")
                Text("Bundled analysis groups speakers and excludes detected overlap. Local sound screening rejects likely music, singing or insufficient speech. It does not identify characters, remove music or train RVC models. Every accepted reference must pass a word check; resemblance needs listening review.").font(.footnote).foregroundStyle(.secondary)
                Button(selected == nil ? "Choose video or audio" : "Choose a different file") { importing = true }
                    .buttonStyle(.bordered).disabled(local.busy).accessibilityIdentifier("local-video-import")
                if selected != nil { Label("Local media selected", systemImage: "doc.fill") }
                TextField("YouTube or supported HTTPS media URL", text: $sourceURL)
                    .textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                    .textFieldStyle(.roundedBorder).disabled(local.busy).accessibilityIdentifier("local-video-url")
                PasteButton(payloadType: String.self) { values in
                    authorized = false
                    guard values.count == 1, let raw = values.first, raw.utf8.count <= 16_384 else {
                        selectionError = "Clipboard must contain one supported video URL of at most 16,384 bytes."
                        return
                    }
                    do {
                        sourceURL = try LocalMediaURLPolicy.input(raw).absoluteString
                        selected = nil
                        selectionError = nil
                    } catch { selectionError = error.localizedDescription }
                }.buttonStyle(.bordered).disabled(local.busy)
                    .accessibilityLabel("Paste video URL from Clipboard")
                    .accessibilityIdentifier("local-video-paste")
                Text("URL acquisition needs internet to contact the source website. Public YouTube pages with direct supported streams, and direct media on upload.wikimedia.org or archive.org, are supported candidates. Sign-in, age checks, encrypted signatures and challenges are not bypassed; those sources need local-file import.").font(.footnote).foregroundStyle(.secondary)
                Toggle("I am authorized to use this media and its voices", isOn: $authorized).disabled(local.busy)
                Button("Generate speaker references") {
                    if let selected { local.start(selected, authorized: authorized, library: library, audio: audio, speech: speech) }
                }.buttonStyle(.borderedProminent).disabled(selected == nil || !authorized || local.busy)
                    .accessibilityIdentifier("local-video-generate")
                Button("Download URL and generate references") {
                    local.startURL(sourceURL, authorized: authorized, library: library, audio: audio, speech: speech)
                }.buttonStyle(.borderedProminent).disabled(sourceURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !authorized || local.busy)
                    .accessibilityIdentifier("local-video-download")
                if let selectionError { Text(selectionError).foregroundStyle(.red) }
                Text(local.notice).accessibilityIdentifier("local-video-status")
                if local.busy {
                    ProgressView("Working on this iPhone…")
                    Button("Pause and retain files") { local.cancel() }.buttonStyle(.bordered)
                } else if let job = local.current, !job.completed, job.sourceFile != nil || job.acquisitionURL != nil {
                    Button("Resume retained job") { local.resume(library: library, audio: audio, speech: speech) }.buttonStyle(.bordered)
                }
                if let reference = local.reference { Button("Listen to reference") { audio.play(reference) }.disabled(local.busy) }
                if let preview = local.preview { Button("Listen to generated preview") { audio.play(preview) }.disabled(local.busy) }
                if let similarity=local.validatedSimilarity() {
                    VStack(alignment:.leading,spacing:4) {
                        Text("Recorded speaker similarity").font(.headline)
                        Text(String(format:"Cosine diagnostic: %.3f",similarity.report.cosineSimilarity)).font(.caption.monospaced())
                        Text("Measured " + similarity.measured.formatted(date:.abbreviated,time:.standard)).font(.caption)
                        Text("This is not a likeness percentage or identity verification. There is no calibrated acceptance threshold. Listen to both clips; the diagnostic describes only this retained reference/preview pair.").font(.caption).foregroundStyle(.secondary)
                    }.accessibilityIdentifier("local-video-similarity")
                }
                if local.current?.voiceID != nil {
                    NavigationLink("Use saved references for new speech") { CharacterLibraryView() }
                }
                if let outcomes = local.current?.speakerOutcomes, !outcomes.isEmpty {
                    Text("Speaker results").font(.headline)
                    ForEach(outcomes.keys.sorted(), id: \.self) { speaker in
                        Text("Unidentified speaker \(speaker): \(outcomes[speaker] ?? "Pending")").font(.caption)
                    }
                }
                if let evidence = local.current?.visualEvidence {
                    DisclosureGroup("Sampled visual evidence") {
                        Text("Visible text is not a verified character name. These frames coincide with a tentative speaker turn, but the actual speaker may be off screen. OCR confidence measures text recognition, not identity.").font(.caption)
                        if evidence.audioOnly { Text("Audio-only source; no frames available.").font(.caption) }
                        ForEach(evidence.frames) { frame in
                            VStack(alignment:.leading,spacing:6) {
                                Text("Unidentified speaker \(frame.speaker) · frame at \(frame.actualSeconds, specifier: "%.2f") s").font(.caption.bold())
                                if let data=local.visualFrameData(frame), let image=UIImage(data:data) {
                                    Image(uiImage:image).resizable().scaledToFit().frame(maxHeight:240)
                                        .accessibilityLabel("Sampled video frame; speaker identity unverified")
                                    ForEach(Array(frame.lines.enumerated()),id:\.offset) { _, line in
                                        Text("Visible text: \(line.text) · OCR \(Int(line.confidence * 100))%").font(.caption).textSelection(.enabled)
                                    }
                                    if frame.lines.isEmpty { Text("No readable English text detected in this frame.").font(.caption) }
                                } else { Text("Retained frame missing or changed; frame and OCR evidence not displayed.").font(.caption) }
                            }
                        }
                        if evidence.omittedSpeakers > 0 { Text("\(evidence.omittedSpeakers) speaker groups were not sampled to limit resource use.").font(.caption) }
                        if evidence.unavailableFrames > 0 { Text("\(evidence.unavailableFrames) requested frames were unavailable.").font(.caption) }
                    }.accessibilityIdentifier("local-video-visual-evidence")
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
                if local.current != nil {
                    DisclosureGroup("Complete retained event history") {
                        Text("Oldest entries first, 100 per page. Older jobs may only have their previously saved snapshot. Refresh reads actual events without changing activity timestamps.").font(.caption)
                        Button("Refresh from first event") { loadJournal(0) }
                        if let journalError { Text(journalError).foregroundStyle(.orange) }
                        if let page=journalPage {
                            Text("Showing \(page.offset + (page.events.isEmpty ? 0 : 1))–\(page.offset + page.events.count) of \(page.total) retained events").font(.caption)
                            ForEach(page.events) { event in
                                Text(event.time.formatted(date:.abbreviated,time:.standard) + " · " + event.stage + "\n" + event.message).font(.caption).textSelection(.enabled)
                            }
                            HStack {
                                if page.offset>0 { Button("Previous 100") { loadJournal(max(0,page.offset-100)) } }
                                if let next=page.next { Button("Next 100") { loadJournal(next) } }
                            }
                            ShareLink("Share this log page",item:page.text)
                        }
                    }.accessibilityIdentifier("local-video-durable-log")
                }
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
        .onChange(of: local.current?.id) { _, _ in journalPage=nil; journalError=nil }
        .onChange(of: sourceURL) { _, _ in authorized = false }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.movie, .audio]) { result in
            switch result {
            case .success(let url): selected = url; authorized = false; selectionError = nil
            case .failure: selectionError = "The selected file could not be opened. No job was started."
            }
        }
    }
    private func loadJournal(_ offset: Int) {
        do { journalPage=try local.journalPage(offset:offset);journalError=nil }
        catch { journalPage=nil;journalError=error.localizedDescription }
    }

}
