import SwiftUI

struct SuggestionsView: View {
    @Environment(\.openURL) private var openURL
    @AppStorage("suggestionDraft.title.v1") private var title = ""
    @AppStorage("suggestionDraft.body.v1") private var details = ""
    @State private var acknowledged = false
    @State private var status = ""
    var body: some View {
        Form {
            Section("Public suggestions") {
                Text("GitHub suggestions are PUBLIC. Anyone can read the text you submit.")
                    .font(.headline).foregroundStyle(.orange).accessibilityIdentifier("suggestion-public-warning")
                Text("Do not include speech text, recordings, private voices, logs, device identifiers or personal information. VoiceMatrix includes only the title and request you type here; nothing is attached automatically.")
                Text("Your draft stays on this iPhone until you choose to open GitHub. GitHub requires sign-in and a separate Submit action. Opening the draft does not send it.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Your request") {
                TextField("Short title", text: $title).accessibilityIdentifier("suggestion-title")
                TextEditor(text: $details).frame(minHeight: 160).accessibilityLabel("Suggestion details")
                Text("Describe the improvement and how you would use it. Keep the request under 2,500 UTF-8 bytes.")
                    .font(.caption).foregroundStyle(.secondary)
                Toggle("I understand that submitted text is public", isOn: $acknowledged)
                Button("Review draft on GitHub") {
                    guard let url = SuggestionDraft.url(title: title, details: details) else { return }
                    openURL(url) { accepted in
                        status = accepted ? "GitHub opened. Review and submit there. This app cannot confirm submission." : "GitHub could not open. Your draft is still saved here."
                    }
                }.disabled(!acknowledged || SuggestionDraft.url(title: title, details: details) == nil)
                    .accessibilityIdentifier("open-suggestion-draft")
                Button("Clear local draft", role: .destructive) { title = ""; details = ""; acknowledged = false; status = "" }
                if !status.isEmpty { Text(status).accessibilityIdentifier("suggestion-status") }
            }
            Section("Follow up") {
                Link("View submitted VoiceMatrix suggestions", destination: SuggestionDraft.listURL)
                Text("Review and completion are separate steps. Requests may need clarification, testing or device access; submission does not guarantee implementation.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.navigationTitle("Suggestions")
    }
}
