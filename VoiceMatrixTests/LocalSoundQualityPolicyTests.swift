import XCTest
@testable import VoiceMatrix
final class LocalSoundQualityPolicyTests: XCTestCase {
    private func frame(_ start:Double,_ end:Double,_ speech:Double,_ music:Double=0.01,_ singing:Double=0.01) -> LocalSoundQualityPolicy.Frame {
        .init(start:start,end:end,speech:speech,music:music,singing:singing)
    }
    func testStrongSpeechDoesNotOverrideMusicOrSinging() {
        XCTAssertFalse(LocalSoundQualityPolicy.evaluate([frame(0,3,0.99,0.3)],duration:3).admitted)
        XCTAssertFalse(LocalSoundQualityPolicy.evaluate([frame(0,3,0.99,0.01,0.3)],duration:3).admitted)
    }
    func testIncompleteCoverageDoesNotBecomeCleanSpeech() {
        XCTAssertFalse(LocalSoundQualityPolicy.evaluate([frame(0,1,0.9),frame(0,1,0.9)],duration:3).admitted)
        XCTAssertFalse(LocalSoundQualityPolicy.evaluate([],duration:3).admitted)
    }
    func testLowRiskSpeechCanPassWithoutClaimingSeparation() {
        let result=LocalSoundQualityPolicy.evaluate([frame(0,2,0.9),frame(1,3,0.8)],duration:3)
        XCTAssertTrue(result.admitted)
        XCTAssertEqual(result.speechCoverage,1,accuracy:0.001)
        XCTAssertTrue(result.reason.contains("not proof"))
    }
    func testNonFiniteScoresAndSilenceFailClosed() {
        XCTAssertFalse(LocalSoundQualityPolicy.evaluate([frame(0,3,.nan)],duration:3).admitted)
        XCTAssertFalse(LocalSoundQualityPolicy.evaluate([frame(0,3,0.01)],duration:3).admitted)
    }
}
