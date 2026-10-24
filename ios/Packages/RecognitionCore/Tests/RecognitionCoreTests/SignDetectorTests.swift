import RecognitionCore
import XCTest

/// Streams run at 100 fps from t = 0 unless noted, so frame k is at k/100 s and
/// every boundary can be hit exactly. Rest line is 0.70; rest wrists sit at 0.85,
/// a raised wrist at 0.50.
final class SignDetectorTests: XCTestCase {
    // MARK: End of a sign

    func testHandsAtRestFor0_40sEndTheSignAtTheFirstRestFrame() {
        // rest 0.00–0.99, active 1.00–1.99, rest 2.00–2.40
        let run = DetectorRun(frames([(.rest, 100), (.active, 100), (.rest, 41)]))

        XCTAssertEqual(run.segments.count, 1)
        assertSegment(run.segments.first, start: 0.80, end: 2.00, reason: nil)
        XCTAssertEqual(run.events(at: 2.39), [], "0.39 s of rest must not end the sign yet")
        XCTAssertEqual(run.events(at: 2.40).count, 2, "the sign ends on the frame 0.40 s into the rest")
    }

    func testHandsAtRestFor0_39sDoNotEndTheSign() {
        // rest 0.00–0.99, active 1.00–1.99, rest 2.00–2.39, active 2.40–2.89, rest 2.90–3.30
        let run = DetectorRun(frames([(.rest, 100), (.active, 100), (.rest, 40), (.active, 50), (.rest, 41)]))

        XCTAssertEqual(run.segments.count, 1)
        assertSegment(run.segments.first, start: 0.80, end: 2.90, reason: nil)
        XCTAssertEqual(run.statuses, [.watching, .signing, .watching])
    }

    func testBodyDropoutBreaksTheRestRun() {
        // active 1.00–1.49, rest 1.50–1.79, one unseen frame at 1.80, rest 1.81–2.21
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.rest, 30), (.unseen, 1), (.rest, 41)]))

        XCTAssertEqual(run.segments.count, 1)
        assertSegment(run.segments.first, start: 0.80, end: 1.81, reason: nil)
        XCTAssertEqual(run.events(at: 2.20), [])
    }

    func testBodyWithoutDetectedWristsCountsAsRest() {
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.noWrists, 41)]))

        assertSegment(run.segments.first, start: 0.80, end: 1.50, reason: nil)
    }

    // MARK: Start of a sign

    func testActiveFor0_10sStartsTheSign() {
        // active 1.00–1.10
        let run = DetectorRun(frames([(.rest, 100), (.active, 11)]))

        XCTAssertEqual(run.events(at: 1.09), [])
        XCTAssertEqual(run.events(at: 1.10), [.status(.signing)])
        XCTAssertEqual(run.detector.state, .signing(start: 0.80))
    }

    func testFidgetShorterThan0_10sIsIgnored() {
        // active 1.00–1.09 only
        let run = DetectorRun(frames([(.rest, 100), (.active, 10), (.rest, 100)]))

        XCTAssertEqual(run.statuses, [.watching])
        XCTAssertEqual(run.segments, [])
    }

    func testBodyDropoutBreaksTheActiveRun() {
        // active 1.00–1.06, unseen 1.07, active 1.08–1.14: neither run reaches 0.10 s
        let run = DetectorRun(frames([(.rest, 100), (.active, 7), (.unseen, 1), (.active, 7), (.rest, 50)]))

        XCTAssertEqual(run.statuses, [.watching])
    }

    func testRaisedWristWithoutShouldersIsNotActive() {
        let hidden = (0..<30).map { k in
            DetectorFrame(t: 1 + Double(k) / 100, body: false, wrists: [NormalizedPoint(x: 0.5, y: 0.2)])
        }
        let run = DetectorRun(frames([(.rest, 100)]) + hidden)

        XCTAssertEqual(run.statuses, [.watching])
    }

    func testWristExactlyOnTheRestLineIsRestAndJustAboveIsActive() {
        func wristFrames(y: Double) -> [DetectorFrame] {
            (0..<50).map { k in
                DetectorFrame(t: Double(k) / 100, body: true, wrists: [NormalizedPoint(x: 0.5, y: y)])
            }
        }

        XCTAssertEqual(DetectorRun(wristFrames(y: 0.70)).statuses, [.watching])
        XCTAssertEqual(DetectorRun(wristFrames(y: 0.6999)).statuses, [.watching, .signing])
    }

    func testOneRaisedWristIsEnough() {
        let frames = (0..<20).map { k in
            DetectorFrame(t: Double(k) / 100, body: true, wrists: [
                NormalizedPoint(x: 0.3, y: 0.9), NormalizedPoint(x: 0.7, y: 0.5),
            ])
        }

        XCTAssertEqual(DetectorRun(frames).statuses, [.watching, .signing])
    }

    // MARK: Pre-roll

    func testStartIsPreRolledBy0_20sBeforeTheFirstActiveFrame() {
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.rest, 41)]))

        assertSegment(run.segments.first, start: 0.80, end: 1.50, reason: nil)
    }

    func testPreRollIsClampedToTheFirstFrameWhenSigningFromTheStart() {
        let run = DetectorRun(frames([(.active, 50), (.rest, 41)], start: 5))

        assertSegment(run.segments.first, start: 5.00, end: 5.50, reason: nil)
    }

    func testPreRollIsClampedToTheFirstFrameWhenLessHistoryThanPreRoll() {
        // stream starts 5.00, active from 5.10: pre-roll would reach 4.90
        let run = DetectorRun(frames([(.rest, 10), (.active, 50), (.rest, 41)], start: 5))

        assertSegment(run.segments.first, start: 5.00, end: 5.60, reason: nil)
    }

    // MARK: Minimum and maximum length

    func testSignOfExactly0_30sIsAccepted() {
        var params = DetectorParams()
        params.preRollS = 0
        // active 1.00–1.29, rest from 1.30
        let run = DetectorRun(frames([(.rest, 100), (.active, 30), (.rest, 41)]), params: params)

        assertSegment(run.segments.first, start: 1.00, end: 1.30, reason: nil)
    }

    func testSignOf0_29sIsRejectedAsTooShort() {
        var params = DetectorParams()
        params.preRollS = 0
        // active 1.00–1.28, rest from 1.29
        let run = DetectorRun(frames([(.rest, 100), (.active, 29), (.rest, 41)]), params: params)

        assertSegment(run.segments.first, start: 1.00, end: 1.29, reason: .tooShort)
        XCTAssertEqual(run.statuses, [.watching, .signing, .watching])
    }

    func testClampedPreRollCanMakeASignTooShort() {
        // active 0.00–0.19 from the very first frame: start clamps to 0.00
        let run = DetectorRun(frames([(.active, 20), (.rest, 41)]))

        assertSegment(run.segments.first, start: 0.00, end: 0.20, reason: .tooShort)
    }

    func testSignLongerThan4sIsRejectedThenCoolsDownUntilRest() {
        // start 0.80; active until 6.99; rest 7.00–7.40
        let run = DetectorRun(frames([(.rest, 100), (.active, 600), (.rest, 41)]))

        XCTAssertEqual(run.segments.count, 1, "cooldown must not start a second sign")
        assertSegment(run.segments.first, start: 0.80, end: 4.81, reason: .tooLong)
        XCTAssertEqual(run.events(at: 4.80), [], "exactly 4.0 s is not too long")
        XCTAssertEqual(run.events(at: 4.81).count, 1, "no status change: cooldown still shows signing")
        XCTAssertEqual(run.events(at: 7.39), [])
        XCTAssertEqual(run.events(at: 7.40), [.status(.watching)])
        XCTAssertEqual(run.statuses, [.watching, .signing, .watching])
    }

    func testSignJustOver4sIsTooLong() {
        // active from 0.00 (start clamps to 0.00), then one frame 4.0005 s in
        var run = DetectorRun(frames([(.active, 401)]))
        XCTAssertEqual(run.segments, [], "4.00 s is still allowed")

        run.feed([FrameScript.frame(.active, at: 4.0005)])

        assertSegment(run.segments.first, start: 0, end: 4.0005, reason: .tooLong)
    }

    func testDetectorWatchesForNewSignsAfterCooldown() {
        var run = DetectorRun(frames([(.rest, 100), (.active, 600), (.rest, 41)]))
        // next sign: active 7.41–7.90, rest from 7.91
        run.feed(frames([(.active, 50), (.rest, 41)], start: 7.41))

        XCTAssertEqual(run.segments.count, 2)
        assertSegment(run.segments.last, start: 7.21, end: 7.91, reason: nil)
    }

    func testCooldownEndsOnlyAfter0_40sOfRest() {
        // too long at 4.81, then rest 4.82–5.21 (0.39 s), active, rest 5.30–5.70
        let run = DetectorRun(frames([(.rest, 100), (.active, 382), (.rest, 40), (.active, 8), (.rest, 41)]))

        XCTAssertEqual(run.events(at: 5.21), [])
        XCTAssertEqual(run.events(at: 5.70), [.status(.watching)])
        XCTAssertEqual(run.segments.count, 1)
    }

    // MARK: Losing the body

    func testLosingTheBodyFor0_50sWhileSigningRejectsTheSign() {
        // active 1.00–1.49, unseen 1.50–2.00
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.unseen, 51)]))

        XCTAssertEqual(run.events(at: 1.99), [])
        XCTAssertEqual(run.events(at: 2.00), [
            .segment(Segment(start: run.segments.first?.start ?? .nan, end: 2.00, reason: .lostTracking)),
            .status(.cantSee),
        ])
        assertSegment(run.segments.first, start: 0.80, end: 2.00, reason: .lostTracking)
        XCTAssertEqual(run.detector.state, .cantSee)
    }

    func testDropoutShorterThan0_50sKeepsTheSign() {
        // active 1.00–1.49, unseen 1.50–1.99, active 2.00–2.19, rest from 2.20
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.unseen, 50), (.active, 20), (.rest, 41)]))

        XCTAssertEqual(run.statuses, [.watching, .signing, .watching])
        XCTAssertEqual(run.segments.count, 1)
        assertSegment(run.segments.first, start: 0.80, end: 2.20, reason: nil)
    }

    func testLosingTheBodyWhileWatchingEmitsNoSegment() {
        let run = DetectorRun(frames([(.rest, 100), (.unseen, 51)]))

        XCTAssertEqual(run.segments, [])
        XCTAssertEqual(run.events(at: 1.50), [.status(.cantSee)])
    }

    func testStaysCantSeeUntilTheBodyReturns() {
        let run = DetectorRun(frames([(.rest, 100), (.unseen, 200)]))

        XCTAssertEqual(run.statuses, [.watching, .cantSee])
        XCTAssertEqual(run.detector.state, .cantSee)
    }

    func testReturningAtRestGoesStraightToWatching() {
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.unseen, 51), (.rest, 1)]))

        XCTAssertEqual(run.events(at: 2.01), [.status(.watching)])
        XCTAssertEqual(run.detector.state, .watching)
    }

    func testReturningWithHandsUpCoolsDownWithoutStartingASign() {
        // unseen 1.00–1.50, active 1.51–2.50, rest 2.51–2.91
        let run = DetectorRun(frames([(.rest, 100), (.unseen, 51), (.active, 100), (.rest, 41)]))

        XCTAssertEqual(run.events(at: 1.51), [.status(.signing)])
        XCTAssertEqual(run.events(at: 2.90), [])
        XCTAssertEqual(run.events(at: 2.91), [.status(.watching)])
        XCTAssertEqual(run.statuses, [.watching, .cantSee, .signing, .watching])
        XCTAssertEqual(run.segments, [], "hands already up on return are never a sign")
    }

    func testCooldownCanAlsoLoseTheBody() {
        let run = DetectorRun(frames([(.rest, 100), (.active, 500), (.unseen, 51)]))

        XCTAssertEqual(run.segments.map(\.reason), [.tooLong], "no lost-tracking segment outside a sign")
        XCTAssertEqual(run.statuses, [.watching, .signing, .cantSee])
    }

    // MARK: Sequences

    func testTwoSignsInARowGiveTwoSegments() {
        // sign 1: active 1.00–1.49, rest 1.50–1.99; sign 2: active 2.00–2.49, rest 2.50–2.90
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.rest, 50), (.active, 50), (.rest, 41)]))

        XCTAssertEqual(run.segments.count, 2)
        assertSegment(run.segments.first, start: 0.80, end: 1.50, reason: nil)
        assertSegment(run.segments.last, start: 1.80, end: 2.50, reason: nil)
        XCTAssertEqual(run.statuses, [.watching, .signing, .watching, .signing, .watching])
    }

    func testFirstFrameReportsTheInitialStatusAndRepeatsAreSilent() {
        var detector = SignDetector(restY: 0.70)

        XCTAssertEqual(detector.update(FrameScript.frame(.rest, at: 0)), [.status(.watching)])
        XCTAssertEqual(detector.update(FrameScript.frame(.rest, at: 0.01)), [])
    }

    func testSegmentIsReportedBeforeTheStatusChangeOnTheSameFrame() {
        let run = DetectorRun(frames([(.rest, 100), (.active, 50), (.rest, 41)]))
        let finalEvents = run.events(at: 1.90)

        XCTAssertEqual(finalEvents.count, 2)
        guard case .segment = finalEvents.first else { return XCTFail("segment must come first") }
        XCTAssertEqual(finalEvents.last, .status(.watching))
    }

    func testCooldownAndSigningShareTheYellowStatus() {
        var detector = SignDetector(restY: 0.70)
        for frame in frames([(.rest, 100), (.active, 500)]) { _ = detector.update(frame) }

        XCTAssertEqual(detector.state, .cooldown)
        XCTAssertEqual(detector.status, .signing)
    }
}
