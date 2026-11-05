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
    func speakLocal() {
        synthesizer.stopSpeaking(at:.immediate)
        let utterance=AVSpeechUtterance(string:text)
        utterance.rate=Float(speed)
        utterance.pitchMultiplier=Float(pitch)
        utterance.voice=AVSpeechSynthesisVoice(identifier:offlineVoiceID) ?? AVSpeechSynthesisVoice(language:"en-US")
        synthesizer.speak(utterance)
        status="Device speech voice (no API). Not an identity clone of \(selected.name)."
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
    @StateObject private var store=VoiceStore()
    @State private var apiKey=""
    var body: some View {
        NavigationStack {
            Form {
                Section("Neural Speech") {
                    NavigationLink("Open Offline Neural Studio") { NeuralStudioView() }
                    NavigationLink("Create Voice Clones from Authorized Samples") { CloneStudioView() }
                }
                Section("Catalog • \(Catalog.all.count) references") {
                    TextField("Search characters, actors, singers",text:$store.search)
                    Picker("Category",selection:$store.category) {
                        Text("All").tag("All")
                        ForEach(["Characters","Actors","Singers","Original Styles"],id:\.self) { Text($0).tag($0) }
                    }
                    List(store.matched,id:\.id) { item in
                        Button {
                            store.choose(item)
                        } label: {
                            HStack {
                                Text(item.name).foregroundStyle(.primary)
                                Spacer()
                                if store.selected.id == item.id { Image(systemName:"checkmark.circle.fill") }
                                else if item.category == "Original Styles" {Image(systemName:"waveform")}
                                else {Image(systemName:"lock").foregroundStyle(.secondary)}
                            }
                        }
                    }.frame(minHeight:200,maxHeight:340)
                }
                Section("Studio • \(store.selected.name)") {
                    TextEditor(text:$store.text).frame(minHeight:75)
                    HStack {
                        Button("System Speech") {store.speakLocal()}
                        Spacer()
                        Button(store.offlineOnly ? "Speak Offline" : "Generate AI") {Task { await store.generate() }}.disabled(store.busy || (!store.offlineOnly && !store.mapped))
                    }
                    if let url=store.output { ShareLink(item:url) {Label("Share AI audio",systemImage:"square.and.arrow.up")} }
                    Text(store.mapped ? "Authorized model configured; generation requires provider access." : "No authorized voice model installed for this identity.")
                        .font(.footnote).foregroundStyle(.secondary)
                    HStack {
                        Button(store.recording ? "Stop Recording" : "Record Mic") {
                            if store.recording {store.stopRecording()} else {Task {await store.startRecording()}}
                        }
                        if store.recorded != nil {
                            Button("Play Recording"){store.playRecording()}
                        }
                    }
                    if let url=store.recorded { ShareLink(item:url) {Label("Share Recording",systemImage:"square.and.arrow.up")} }
                }
                Section("Free Offline Voices") {
                    Toggle("Offline-only mode", isOn: $store.offlineOnly)
                    Text("Browse every speech voice installed in iOS, across languages. Additional system voices must be installed using iOS settings. These are genuine system voices, not celebrity clones.")
                        .font(.footnote).foregroundStyle(.secondary)
                    Picker("Any installed device voice", selection: $store.offlineVoiceID) {
                        Text("Default system voice").tag("")
                        ForEach(store.installedVoices, id: \.identifier) { v in
                            Text("\(v.name) (\(v.language))").tag(v.identifier)
                        }
                    }
                    Button("Preview offline voice") { store.speakLocal() }
                }
                Section("Optional Online Neural Model Setup") {
                    TextField("HTTPS /v1/audio/speech endpoint",text:$store.endpoint).textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("Provider API key",text:$apiKey)
                    Button("Save API Key") {store.saveKey(apiKey);apiKey=""}
                    TextField("Model identifier",text:$store.model).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Voice identifier",text:$store.voice).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Toggle("I have authorization for this voice",isOn:$store.authorized)
                    Button("Save mapping for \(store.selected.name)") {store.saveMapping()}
                    Text("Catalog names are not preinstalled voice clones. Only connect models you have the rights to use. AI requests send text to your selected provider.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Status") {Text(store.status).font(.footnote)}
            }
            .navigationTitle("GHOSTLINE")
        }
    }
}
