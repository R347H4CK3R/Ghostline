import Foundation
@main struct Checks {
    static func main() {
        func frame(_ speech:Double,_ music:Double=0.01,_ singing:Double=0.01)->LocalSoundQualityPolicy.Frame { .init(start:0,end:3,speech:speech,music:music,singing:singing) }
        precondition(!LocalSoundQualityPolicy.evaluate([frame(0.99,0.3)],duration:3).admitted)
        precondition(!LocalSoundQualityPolicy.evaluate([frame(0.99,0.01,0.3)],duration:3).admitted)
        precondition(LocalSoundQualityPolicy.evaluate([frame(0.9)],duration:3).admitted)
        precondition(!LocalSoundQualityPolicy.evaluate([frame(0.01)],duration:3).admitted)
        precondition(!LocalSoundQualityPolicy.evaluate([frame(.nan)],duration:3).admitted)
        precondition(!LocalSoundQualityPolicy.evaluate([],duration:3).admitted)
        let partial=LocalSoundQualityPolicy.Frame(start:0,end:1,speech:0.9,music:0,singing:0)
        precondition(!LocalSoundQualityPolicy.evaluate([partial,partial],duration:3).admitted)
        print("Independent-score and temporal-coverage policy passed; not classifier accuracy evidence.")
    }
}
