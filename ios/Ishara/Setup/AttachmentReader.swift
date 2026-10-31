import CallSession
import Foundation
import PDFKit
import UIKit
import Vision

/// A photo or PDF the user attached to the request. Its text is read on this iPhone and goes
/// with the brief as a document, so Ishara can quote it (word for word, only when asked).
struct Attachment: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let thumbnail: UIImage?
    let text: String
    var problem: String?

    var summary: String {
        problem ?? "Read on this iPhone · Ishara can quote it when asked"
    }

    var document: Document? {
        problem == nil && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? Document(name: name, text: text) : nil
    }
}

enum AttachmentReader {
    /// Reads the text with Vision (photos) or PDFKit (PDFs, falling back to Vision for scans).
    static func read(data: Data, name: String) async -> Attachment {
        if let pdf = PDFDocument(data: data) {
            var text = (0..<pdf.pageCount).compactMap { pdf.page(at: $0)?.string }.joined(separator: "\n")
            let thumb = pdf.page(at: 0)?.thumbnail(of: CGSize(width: 120, height: 120), for: .mediaBox)
            if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, let first = pdf.page(at: 0) {
                text = await recognise(first.thumbnail(of: CGSize(width: 1600, height: 1600), for: .mediaBox))
            }
            return attachment(name: name, thumbnail: thumb, text: text)
        }
        guard let image = UIImage(data: data) else {
            return Attachment(name: name, thumbnail: nil, text: "", problem: "Couldn't open this file.")
        }
        return attachment(name: name, thumbnail: image, text: await recognise(image))
    }

    private static func attachment(name: String, thumbnail: UIImage?, text: String) -> Attachment {
        let text = String(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(20_000))
        return Attachment(name: name, thumbnail: thumbnail, text: text, problem: text.isEmpty ? "No text found in it." : nil)
    }

    private static func recognise(_ image: UIImage) async -> String {
        guard let cgImage = image.cgImage else { return "" }
        let orientation = CGImagePropertyOrientation(image.imageOrientation)
        return await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .userInitiated).async {
                // Vision objects stay on the worker that creates and performs them.
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .accurate
                request.usesLanguageCorrection = true
                let handler = VNImageRequestHandler(cgImage: cgImage, orientation: orientation)
                do {
                    try handler.perform([request])
                    let lines = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
                    continuation.resume(returning: lines.joined(separator: "\n"))
                } catch {
                    continuation.resume(returning: "")
                }
            }
        }
    }
}

private extension CGImagePropertyOrientation {
    init(_ orientation: UIImage.Orientation) {
        switch orientation {
        case .up: self = .up
        case .down: self = .down
        case .left: self = .left
        case .right: self = .right
        case .upMirrored: self = .upMirrored
        case .downMirrored: self = .downMirrored
        case .leftMirrored: self = .leftMirrored
        case .rightMirrored: self = .rightMirrored
        @unknown default: self = .up
        }
    }
}

/// A selected document must finish reading or be removed before a call can start.
extension Attachment {
    static func callProblem(_ attachments: [Attachment], reading: Int) -> String? {
        if reading > 0 { return "Reading your attachment… Wait before calling." }
        if let failed = attachments.first(where: { $0.document == nil }) {
            return "Couldn’t read \(failed.name). Remove it and attach a readable file before calling."
        }
        return nil
    }
}
