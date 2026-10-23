import RecognitionCore
import XCTest

/// Frames at 100 fps (one frame per 0.01 s) from `start`, built from (posture, frame count) spans.
func frames(
    _ spans: [(FrameScript.Posture, Int)],
    fps: Double = 100,
    start: Double = 0
) -> [DetectorFrame] {
    var script = FrameScript(fps: fps, startTime: start)
    for (posture, count) in spans {
        script.add(posture, frames: count)
    }
    return script.frames
}

func assertSegment(
    _ segment: Segment?,
    start: Double,
    end: Double,
    reason: Segment.RejectionReason?,
    accuracy: Double = 1e-6,
    file: StaticString = #filePath,
    line: UInt = #line
) {
    guard let segment else {
        return XCTFail("Expected a segment, got none", file: file, line: line)
    }
    XCTAssertEqual(segment.start, start, accuracy: accuracy, "start", file: file, line: line)
    XCTAssertEqual(segment.end, end, accuracy: accuracy, "end", file: file, line: line)
    XCTAssertEqual(segment.reason, reason, "reason", file: file, line: line)
    XCTAssertEqual(segment.accepted, reason == nil, "accepted", file: file, line: line)
}
