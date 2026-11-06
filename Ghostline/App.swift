import SwiftUI
import AVFoundation
import Security

struct VoiceItem: Identifiable, Hashable {
    let name: String
    let category: String
    var id: String { category + "/" + name }
}
enum Catalog {
    static let groups: [(String,String)] = [
      ("Characters","Ghostface|Darth Vader|The Joker|Batman|Bane|Harley Quinn|Superman|Gollum|Gandalf|Saruman|Sauron|Yoda|Emperor Palpatine|Kylo Ren|Obi-Wan Kenobi|Han Solo|C-3PO|R2-D2|Optimus Prime|Megatron|Bumblebee|Freddy Krueger|Michael Myers|Jason Voorhees|Chucky|Pennywise|Jigsaw|Hannibal Lecter|Beetlejuice|Wednesday Addams|Morticia Addams|The Grinch|Shrek|Donkey|Puss in Boots|SpongeBob SquarePants|Patrick Star|Squidward|Homer Simpson|Bart Simpson|Marge Simpson|Peter Griffin|Stewie Griffin|Brian Griffin|Rick Sanchez|Morty Smith|Eric Cartman|Kenny McCormick|Sonic|Mario|Luigi|Bowser|Master Chief|Cortana|Kratos|Arthur Morgan|John Marston|Trevor Philips|Michael De Santa|Franklin Clinton|Geralt of Rivia|Voldemort|Severus Snape|Dumbledore|Harry Potter|Hermione Granger|Draco Malfoy|Iron Man|Loki|Thor|Thanos|Deadpool|Wolverine|Venom|Spider-Man|Doctor Strange|Captain Jack Sparrow|Davy Jones|The Terminator|HAL 9000|Wednesday’s Thing"),
      ("Actors","Roger L. Jackson|Morgan Freeman|Samuel L. Jackson|James Earl Jones|Mark Hamill|Kevin Conroy|Heath Ledger|Joaquin Phoenix|Christian Bale|Michael Keaton|Robert Pattinson|Tom Hardy|Benedict Cumberbatch|Alan Rickman|Ian McKellen|Christopher Lee|Patrick Stewart|Liam Neeson|Keanu Reeves|Ryan Reynolds|Hugh Jackman|Robert Downey Jr.|Chris Hemsworth|Tom Hiddleston|Pedro Pascal|Giancarlo Esposito|Bryan Cranston|Aaron Paul|Jack Black|Jim Carrey|Robin Williams|Eddie Murphy|Mike Myers|Seth MacFarlane|Tara Strong|Nancy Cartwright|Dan Castellaneta|H. Jon Benjamin|Keith David|Clancy Brown|Tony Todd|Vincent Price|Boris Karloff|Tim Curry|Bill Skarsgård|Matthew Lillard|Neve Campbell|Courteney Cox|Jamie Lee Curtis|Sigourney Weaver|Scarlett Johansson|Emma Stone|Cate Blanchett|Viola Davis|Meryl Streep|Denzel Washington|Idris Elba|Jason Statham|Arnold Schwarzenegger|Sylvester Stallone|Al Pacino|Robert De Niro"),
      ("Singers","Michael Jackson|Elvis Presley|Freddie Mercury|Whitney Houston|Mariah Carey|Ariana Grande|Beyoncé|Rihanna|Taylor Swift|Billie Eilish|Lady Gaga|Adele|Bruno Mars|The Weeknd|Ed Sheeran|Justin Bieber|Harry Styles|Dua Lipa|Sia|Katy Perry|Miley Cyrus|Lana Del Rey|Olivia Rodrigo|Sabrina Carpenter|Shakira|Bad Bunny|Karol G|Rosalía|Drake|Kendrick Lamar|Eminem|Snoop Dogg|Tupac Shakur|The Notorious B.I.G.|Nicki Minaj|Cardi B|Doja Cat|Post Malone|Travis Scott|Kanye West|J. Cole|Lil Wayne|Future|Johnny Cash|Dolly Parton|Willie Nelson|George Strait|Chris Stapleton|Luke Combs|Morgan Wallen|Jelly Roll|Zach Bryan|Reba McEntire|Carrie Underwood|Kacey Musgraves|Frank Sinatra|Dean Martin|Louis Armstrong|Aretha Franklin|Stevie Wonder|Prince|David Bowie|Ozzy Osbourne|James Hetfield|Chester Bennington|Kurt Cobain|Dave Grohl|Axl Rose|Bon Jovi|Amy Winehouse|Céline Dion|Andrea Bocelli"),
      ("Original Styles","Masked Caller|Gothic Narrator|Midnight Radio|Haunted Whisper|Robot Sentinel|Galactic Tyrant|Animated Trickster|Epic Trailer|Southern Outlaw|Space Captain|Arcane Sorcerer|Creature Growl|Arena Announcer|Noir Detective|Retro Robot|Pop Ballad|Soulful Crooner|Rock Frontman|Country Storyteller|Hip-Hop Host")
    ]
    static let all: [VoiceItem] = groups.flatMap { pair in pair.1.split(separator: "|").map { VoiceItem(name: String($0),category:pair.0) } }
}
struct ModelBinding: Codable { var model: String; var voice: String; var authorized: Bool }
@MainActor final class VoiceStore: NSObject, ObservableObject {
    @Published var selected = Catalog.all[0]
    @Published var text = "What's your favorite scary movie?"
    @Published var search = ""
    @Published var category = "All"
    @Published var status = "Select an original style or map an authorized neural model."
    @Published var endpoint = UserDefaults.standard.string(forKey: "endpoint") ?? ""
    @Published var model = ""
    @Published var voice = ""
    @Published var authorized = false
    @Published var output: URL?
    @Published var recording = false
    @Published var recorded: URL?
    @Published var pitch = 0.8
    @Published var speed = 0.48
    @Published var busy = false
    @Published var offlineVoiceID = UserDefaults.standard.string(forKey: "offlineVoiceID") ?? ""
    @Published var offlineOnly = true
    var installedVoices: [AVSpeechSynthesisVoice] {
        AVSpeechSynthesisVoice.speechVoices().sorted { a, b in a.language == b.language ? a.name < b.name : a.language < b.language }
    }
    func chooseOfflineVoice(_ id: String) {
        offlineVoiceID = id
        UserDefaults.standard.set(id, forKey: "offlineVoiceID")
        if let v = AVSpeechSynthesisVoice(identifier: id) { status = "Selected installed offline voice: \(v.name)" }
    }
    private let synthesizer = AVSpeechSynthesizer()
    private var player: AVAudioPlayer?
    private var recorder: AVAudioRecorder?
    private var mappings: [String:ModelBinding] = [:]
    override init() {
        super.init()
        if let data = UserDefaults.standard.data(forKey:"bindings"),
           let decoded = try? JSONDecoder().decode([String:ModelBinding].self,from:data) { mappings = decoded }
        loadMapping()
    }
    func loadMapping() {
        let b = mappings[selected.id]
        model = b?.model ?? ""
        voice = b?.voice ?? ""
        authorized = b?.authorized ?? false
    }
    func choose(_ item: VoiceItem) { selected = item; loadMapping(); output = nil }
    var matched: [VoiceItem] {
        Catalog.all.filter { (category == "All" || $0.category == category) && (search.isEmpty || $0.name.localizedCaseInsensitiveContains(search)) }
    }
    func saveMapping() {
        mappings[selected.id] = ModelBinding(model:model.trimmingCharacters(in:.whitespacesAndNewlines),voice:voice.trimmingCharacters(in:.whitespacesAndNewlines),authorized:authorized)
        if let data = try? JSONEncoder().encode(mappings) { UserDefaults.standard.set(data,forKey:"bindings") }
        UserDefaults.standard.set(endpoint,forKey:"endpoint")
        status = "Model configuration saved. Test generation to verify availability."
    }
    var mapped: Bool {
        guard let b = mappings[selected.id] else { return false }
        return b.authorized && !b.model.isEmpty && !b.voice.isEmpty
    }
    func saveKey(_ key: String) {
        let q:[String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrAccount as String:"ghostline.api"]
        SecItemDelete(q as CFDictionary)
        guard !key.isEmpty else { status = "API key cleared"; return }
        var data=q;data[kSecValueData as String]=Data(key.utf8);data[kSecAttrAccessible as String]=kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        status = SecItemAdd(data as CFDictionary,nil) == errSecSuccess ? "API key saved in Keychain" : "Unable to save API key"
    }
    private func apiKey() -> String? {
        let q:[String:Any] = [kSecClass as String:kSecClassGenericPassword,kSecAttrAccount as String:"ghostline.api",kSecReturnData as String:true,kSecMatchLimit as String:kSecMatchLimitOne]
        var output:CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary,&output) == errSecSuccess,let bytes=output as? Data else { return nil }
        return String(data:bytes,encoding:.utf8)
    }
    // Never substitute an ordinary system TTS voice for a selected celebrity,
    // character, or singer. Those identities require an installed, verified model.
    func speakLocal() {
        synthesizer.stopSpeaking(at: .immediate)
        status = "No verified offline identity model for \(selected.name). Use a supported neural studio or import an authorized RVC voice; system speech will not impersonate this identity."
    }

    // Explicitly separate ordinary iOS system-voice preview from identity speech.
    func previewSystemVoice() {
        synthesizer.stopSpeaking(at: .immediate)
        let sample = "This is an Apple system voice preview, not a character or celebrity voice."
        let utterance = AVSpeechUtterance(string: sample)
        utterance.rate = Float(speed)
        utterance.pitchMultiplier = Float(pitch)
        utterance.voice = AVSpeechSynthesisVoice(identifier: offlineVoiceID)
            ?? AVSpeechSynthesisVoice(language: "en-US")
        synthesizer.speak(utterance)
        status = "Playing an iOS system voice preview. No character identity is claimed."
    }
    func generate() async {
        if offlineOnly { speakLocal(); return }
        guard mapped,let binding=mappings[selected.id] else { status="No authorized model mapped for this entry";return }
        guard let url=URL(string:endpoint),url.scheme == "https",url.host != nil,url.user == nil,url.password == nil else {status="Enter a valid HTTPS API speech endpoint";return}
        guard let key=apiKey(),!key.isEmpty else {status="Save the provider API key first";return}
        guard !text.isEmpty else {status="Enter text first";return}
        busy=true;defer{busy=false}
        do {
            var request=URLRequest(url:url)
            request.httpMethod="POST"
            request.timeoutInterval=90
            request.setValue("Bearer \(key)",forHTTPHeaderField:"Authorization")
            request.setValue("application/json",forHTTPHeaderField:"Content-Type")
            request.httpBody=try JSONSerialization.data(withJSONObject:["model":binding.model,"voice":binding.voice,"input":text,"response_format":"mp3"])
            let (data,response)=try await URLSession.shared.data(for:request)
            guard let http=response as? HTTPURLResponse,(200...299).contains(http.statusCode) else { status="Provider error. Check credentials and voice model.";return }
            let mime=(http.value(forHTTPHeaderField:"Content-Type") ?? "").lowercased()
            guard data.count > 128,data.count < 50_000_000,!mime.contains("json"),!mime.contains("html") else { status="Provider did not return playable audio";return }
            let path=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".mp3")
            try data.write(to:path,options:.atomic)
            let test=try AVAudioPlayer(contentsOf:path)
            guard test.prepareToPlay() else {status="Invalid MP3 returned";return}
            player=test
            output=path
            try AVAudioSession.sharedInstance().setCategory(.playback,mode:.default)
            try AVAudioSession.sharedInstance().setActive(true)
            _ = test.play()
            status="Generated audio for \(selected.name) using configured provider"
        } catch {status="Generation failed: \(error.localizedDescription)"}
    }
    func startRecording() async {
        let granted=await withCheckedContinuation { (continuation: CheckedContinuation<Bool,Never>) in AVAudioApplication.requestRecordPermission { continuation.resume(returning:$0) } }
        guard granted else {status="Microphone access denied";return}
        do {
            try AVAudioSession.sharedInstance().setCategory(.playAndRecord,mode:.default,options:[.defaultToSpeaker])
            try AVAudioSession.sharedInstance().setActive(true)
            let url=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+".caf")
            let settings:[String:Any]=[AVFormatIDKey:Int(kAudioFormatLinearPCM),AVSampleRateKey:44100,AVNumberOfChannelsKey:1,AVLinearPCMBitDepthKey:16]
            let recorder=try AVAudioRecorder(url:url,settings:settings)
            guard recorder.record() else {status="Could not start microphone";return}
            self.recorder=recorder;recorded=url;recording=true;status="Recording"
        } catch {status="Microphone failed: \(error.localizedDescription)"}
    }
    func stopRecording() {recorder?.stop();recorder=nil;recording=false;status="Recording saved"}
    func playRecording() {
        guard let url=recorded else{return}
        do {
            try AVAudioSession.sharedInstance().setCategory(.playback)
            try AVAudioSession.sharedInstance().setActive(true)
            let p=try AVAudioPlayer(contentsOf:url);player=p;_ = p.play();status="Playing original recording"
        } catch {status="Cannot play recording: \(error.localizedDescription)"}
    }
}
@main struct GhostlineApp: App {
    var body: some Scene { WindowGroup { ContentView() } }
}
struct ContentView: View {
    private let accent = Color(red: 0.67, green: 0.36, blue: 1.0)
    var body: some View {
        TabView {
            NavigationStack { GhostlineHomeView() }
                .tabItem { Label("Home", systemImage: "house.fill") }
            NavigationStack { GhostlineLibraryView() }
                .tabItem { Label("Library", systemImage: "square.stack.3d.up.fill") }
            NavigationStack { GhostlineGeneratorView() }
                .tabItem { Label("Generate", systemImage: "waveform") }
            NavigationStack { RVCPackLibraryView() }
                .tabItem { Label("RVC Packs", systemImage: "shippingbox.fill") }
            NavigationStack { GhostlineToolsView() }
                .tabItem { Label("Tools", systemImage: "slider.horizontal.3") }
        }
        .tint(accent)
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("GhostlineTabbedRoot")
    }
}

private struct GhostlineFeatureRow: View {
    let icon: String
    let heading: String
    let detail: String
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: icon)
                .font(.title2)
                .frame(width: 40, height: 40)
                .foregroundStyle(Color(red: 0.75, green: 0.5, blue: 1))
                .background(.purple.opacity(0.17), in: RoundedRectangle(cornerRadius: 12))
            VStack(alignment: .leading, spacing: 3) {
                Text(heading).font(.headline)
                Text(detail).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
        }
        .padding(12)
        .background(.white.opacity(0.055), in: RoundedRectangle(cornerRadius: 16))
    }
}

struct GhostlineHomeView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 17) {
                VStack(alignment: .leading, spacing: 12) {
                    Image(systemName: "waveform.path")
                        .font(.system(size: 47))
                        .foregroundStyle(.purple)
                    Text("GHOSTLINE").font(.largeTitle.bold())
                    Text("RVC Offline Test • New five-tab interface")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.purple)
                    Text("Your private, offline-first voice studio")
                        .font(.subheadline).foregroundStyle(.secondary)
                    HStack {
                        Label("Offline-first", systemImage: "iphone")
                        Spacer()
                        Label("Private packs", systemImage: "lock.shield")
                    }.font(.caption).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(22)
                .background(
                    LinearGradient(colors: [.purple.opacity(0.34), .indigo.opacity(0.12), .black],
                                   startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: RoundedRectangle(cornerRadius: 24)
                )

                Text("Voice workspaces").font(.title3.bold())
                NavigationLink(destination: GhostlineRVCWebScreen()) {
                    GhostlineFeatureRow(icon: "waveform.path", heading: "Offline RVC Converter",
                                        detail: "ContentVec + RMVPE + RVC v2 WebAssembly inference")
                }.buttonStyle(.plain)
                NavigationLink(destination: RVCPackLibraryView()) {
                    GhostlineFeatureRow(icon: "shippingbox", heading: "RVC Pack Library",
                                        detail: "Import private .pth / .index candidates")
                }.buttonStyle(.plain)
                NavigationLink(destination: RVCCoreMLModelView()) {
                    GhostlineFeatureRow(icon: "cpu", heading: "RVC Core ML Test",
                                        detail: "Load converted Core ML models on iPhone")
                }.buttonStyle(.plain)
                NavigationLink(destination: CloneStudioView()) {
                    GhostlineFeatureRow(icon: "mic.fill", heading: "Clone Studio",
                                        detail: "Authorized reference voice recordings")
                }.buttonStyle(.plain)
                NavigationLink(destination: KokoroOfflineView()) {
                    GhostlineFeatureRow(icon: "waveform", heading: "Kokoro Neural Voices",
                                        detail: "Download once, synthesize locally")
                }.buttonStyle(.plain)
                NavigationLink(destination: NeuralStudioView()) {
                    GhostlineFeatureRow(icon: "person.wave.2", heading: "PocketTTS Presets",
                                        detail: "Original and licensed synthetic presets")
                }.buttonStyle(.plain)
                NavigationLink(destination: GhostlineIncludedPiperView()) {
                    GhostlineFeatureRow(icon: "waveform.path", heading: "Included Piper Test Voices",
                        detail: "Source-pinned open-license voices - UNVERIFIED")
                }.buttonStyle(.plain)
                NavigationLink(destination: PiperVoiceLabView()) {
                    GhostlineFeatureRow(icon: "waveform.badge.mic", heading: "Piper Test Lab",
                                        detail: "Unverified multispeaker model candidates")
                }.buttonStyle(.plain)

                VStack(alignment: .leading, spacing: 8) {
                    Text("Authentic identity verification").font(.headline)
                    Text("0 verified movie, animation, performer or singer voices")
                        .font(.subheadline).foregroundStyle(.secondary)
                    ProgressView(value: 0, total: 1)
                    Text("Model imports and catalog names do not count as offline iPhone audio verification.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .padding(16)
                .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))
            }
            .padding(18)
        }
        .navigationTitle("Home")
    }
}

struct GhostlineLibraryView: View {
    private let categories: [(String, String)] = [
        ("Movies & film", "film"), ("Television", "tv"),
        ("Cartoons", "face.smiling"), ("Anime", "sparkles"),
        ("Gaming", "gamecontroller"), ("Singers", "music.mic"),
        ("Celebrities", "star"), ("Original voices", "waveform")
    ]
    var body: some View {
        List {
            Section {
                Text("This library lists verified authentic voices only. No actor, character, or singer identity has been established by an offline iPhone test.")
                    .font(.footnote).foregroundStyle(.secondary)
                Label("0 authentic identities verified", systemImage: "checkmark.shield")
            }
            Section("Browse categories") {
                ForEach(categories.indices, id: \.self) { index in
                    HStack {
                        Label(categories[index].0, systemImage: categories[index].1)
                        Spacer()
                        Text("0 verified").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            Section("Local voice sources") {
                NavigationLink("Offline RVC v2 conversion") { GhostlineRVCWebScreen() }
                NavigationLink("RVC imported packs (not yet playable)") { RVCPackLibraryView() }
                NavigationLink("RVC Core ML model testing") { RVCCoreMLModelView() }
                NavigationLink("Offline PocketTTS presets") { NeuralStudioView() }
                NavigationLink("Offline Kokoro presets") { KokoroOfflineView() }
                NavigationLink("Piper experimental speakers") { PiperVoiceLabView() }
            }
        }.navigationTitle("Voice Library")
    }
}

struct GhostlineGeneratorView: View {
    var body: some View {
        List {
            Section("Generate offline speech") {
                NavigationLink("Kokoro — neural text to speech") { KokoroOfflineView() }
                NavigationLink("PocketTTS — synthetic voice presets") { NeuralStudioView() }
                NavigationLink("Clone Studio — authorized reference audio") { CloneStudioView() }
                NavigationLink("Piper — local speaker testing") { PiperVoiceLabView() }
            }
            Section("RVC conversion") {
                NavigationLink("Convert RVC v2 voice offline") { GhostlineRVCWebScreen() }
                NavigationLink("Import voice packs") { RVCPackLibraryView() }
                NavigationLink("Load converted Core ML model") { RVCCoreMLModelView() }
                Text("Offline RVC inference uses locally imported converted v2 ONNX models. Raw .pth models still need conversion. Compatible model packs and physical-device performance require testing.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }.navigationTitle("Generate")
    }
}

struct GhostlineToolsView: View {
    @StateObject private var store = VoiceStore()
    var body: some View {
        Form {
            Section("System voices • separate from identities") {
                Picker("iOS voice", selection: $store.offlineVoiceID) {
                    Text("System default").tag("")
                    ForEach(store.installedVoices, id: \.identifier) { voice in
                        Text("\(voice.name) (\(voice.language))").tag(voice.identifier)
                    }
                }
                Button("Preview system voice (not a character)") { store.previewSystemVoice() }
                Text(store.status).font(.caption).foregroundStyle(.secondary)
            }
            Section("Verification") {
                Text("Authentic identities: 0 verified on target iPhone")
                Text("Keep the device offline after required model setup. Compare actual audio with authorized reference recordings. This application never certifies identities from catalog names alone.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Privacy") {
                Label("Imported RVC files stored only in local app storage", systemImage: "lock")
                Label("No automatic model or microphone uploads", systemImage: "iphone")
            }
        }.navigationTitle("Tools")
    }
}
