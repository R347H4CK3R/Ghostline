# VoiceMatrix interface refresh
Chris reports that voice playback now works and requests a more appealing, easier interface. Prior direction authorizes autonomous implementation and testing.

Use native SwiftUI with dark ink surfaces, violet accents and teal secondary actions. Retain Home, Voices, Saved, Help and Settings destinations so existing workflows stay recognizable. Make the selected voice prominent and replace the long inline collection with a searchable sheet supporting one-tap selection. Keep reference listening, playback errors and Stop visible. Place import/sync in collection management; keep creation steps short and avoid technical prose in the main flow.

Alternatives considered: merely restyling the long list leaves selection hard to find; replacing navigation and audio state together introduces unnecessary risk. Choose a presentation-only restructure around the current CharacterLibrary and AudioStore APIs. This is the implementer's design choice under the user's autonomous-work instruction.

Preserve audio engines, imported storage paths, saved data, model pins, pairing and playback ownership. No stock profiles. No claims beyond the user's report that voices now work. Native automated tests do not verify individual character resemblance.

Verify empty flows, synthetic collection import, search/selection, reference progress/Stop, restart persistence, cancellation and tabs. Simulator fixtures must never enter a release IPA. Run compile, existing playback/updater tests and workflow UI tests before integration. Release only after package/audio gates; retain0.4.3 feeds until a verified replacement exists.
