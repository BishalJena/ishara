import SwiftUI

/// Maps normalized points of the upright camera image onto a view that shows that image
/// aspect-filled and, for the front camera, mirrored.
struct PreviewMapping {
    let imageSize: CGSize
    let viewSize: CGSize
    var mirrored = true

    private var shownSize: CGSize {
        let scale = max(viewSize.width / imageSize.width, viewSize.height / imageSize.height)
        return CGSize(width: imageSize.width * scale, height: imageSize.height * scale)
    }

    func point(_ normalized: CGPoint) -> CGPoint {
        let shown = shownSize
        let x = mirrored ? 1 - normalized.x : normalized.x
        return CGPoint(
            x: (viewSize.width - shown.width) / 2 + x * shown.width,
            y: (viewSize.height - shown.height) / 2 + normalized.y * shown.height)
    }

    func y(_ normalizedY: Double) -> CGFloat {
        point(CGPoint(x: 0, y: normalizedY)).y
    }
}

/// Dots on the tracked shoulders and wrists, and a dashed rest line once calibration has
/// found it: lift a hand above the line to start a sign. Reads `camera.overlay` here only,
/// so new frames redraw this layer and nothing else.
struct BodyOverlayView: View {
    let camera: LiveCamera

    var body: some View {
        Canvas { context, size in
            guard let overlay = camera.overlay else { return }
            let mapping = PreviewMapping(imageSize: overlay.imageSize, viewSize: size)
            if let restY = overlay.restY {
                let y = mapping.y(restY)
                var line = Path()
                line.move(to: CGPoint(x: 0, y: y))
                line.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(line, with: .color(.orange), style: StrokeStyle(lineWidth: 2, dash: [8, 6]))
            }
            for shoulder in overlay.shoulders {
                context.fill(dot(at: mapping.point(shoulder), radius: 5), with: .color(.white))
            }
            for wrist in overlay.wrists {
                let center = mapping.point(wrist)
                context.fill(dot(at: center, radius: 8), with: .color(.yellow))
                context.stroke(dot(at: center, radius: 8), with: .color(.black.opacity(0.6)), lineWidth: 1.5)
            }
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func dot(at center: CGPoint, radius: CGFloat) -> Path {
        Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2))
    }
}
