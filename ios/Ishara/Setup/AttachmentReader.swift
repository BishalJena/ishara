import CallSession
import Foundation
import PDFKit
import UIKit
import Vision

/// A photo or PDF the user attached to the request, read on this iPhone. Nothing of it leaves
/// the phone: only the details the user keeps as chips are sent with the brief.
struct Attachment: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let thumbnail: UIImage?
    var details: [Detail]
    var problem: String?
}

enum AttachmentReader {
    /// Reads the text with Vision (photos) or PDFKit (PDFs, falling back to Vision for scans)
    /// and picks out the details worth sharing on a call.
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
            return Attachment(name: name, thumbnail: nil, details: [], problem: "Couldn't open this file.")
        }
        return attachment(name: name, thumbnail: image, text: await recognise(image))
    }

    private static func attachment(name: String, thumbnail: UIImage?, text: String) -> Attachment {
        let details = DetailExtractor.extract(from: text)
        return Attachment(
            name: name, thumbnail: thumbnail, details: details,
            problem: details.isEmpty ? (text.isEmpty ? "No text found in it." : "No details found to share.") : nil)
    }

    private static func recognise(_ image: UIImage) async -> String {
        guard let cgImage = image.cgImage else { return "" }
        return await withCheckedContinuation { continuation in
            let request = VNRecognizeTextRequest { request, _ in
                let lines = (request.results as? [VNRecognizedTextObservation] ?? [])
                    .compactMap { $0.topCandidates(1).first?.string }
                continuation.resume(returning: lines.joined(separator: "\n"))
            }
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = true
            let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .init(image.imageOrientation))
            DispatchQueue.global(qos: .userInitiated).async {
                if (try? handler.perform([request])) == nil { continuation.resume(returning: "") }
            }
        }
    }
}

/// Finds the fields a receptionist tends to ask for: "Label: value" lines, and dates, policy
/// or member numbers and phone numbers near a word that names them. Deterministic on purpose:
/// what it finds is shown as chips the user can drop, never sent unseen.
enum DetailExtractor {
    private static let knownLabels: [(pattern: String, label: String)] = [
        (#"(?i)\b(date of birth|dob|birth date|born)\b"#, "Date of birth"),
        (#"(?i)\b(policy (?:no|number|#)?|policy)\b"#, "Policy number"),
        (#"(?i)\b(member(?:ship)? (?:no|number|id)|member id)\b"#, "Member ID"),
        (#"(?i)\b(insurer|insurance|provider|plan)\b"#, "Insurer"),
        (#"(?i)\b(patient(?: name)?|name|insured|holder)\b"#, "Name on the card"),
        (#"(?i)\b(group (?:no|number)|group)\b"#, "Group number"),
        (#"(?i)\b(valid (?:till|until|thru|through)|expiry|expires|exp)\b"#, "Valid until"),
        (#"(?i)\b(phone|mobile|tel|contact)\b"#, "Phone"),
        (#"(?i)\b(address)\b"#, "Address"),
    ]

    static func extract(from text: String) -> [Detail] {
        var found: [Detail] = []
        let lines = text.split(whereSeparator: \.isNewline).map { $0.trimmingCharacters(in: .whitespaces) }
        for (index, line) in lines.enumerated() {
            // "Label: value" or "Label - value" on one line.
            if let range = line.range(of: #"\s*[:\-–]\s+"#, options: .regularExpression),
               line.distance(from: line.startIndex, to: range.lowerBound) <= 32 {
                let label = String(line[..<range.lowerBound]), value = String(line[range.upperBound...])
                add(label: canonical(label) ?? label.capitalized, value: value, to: &found)
                continue
            }
            // A label on its own line with the value on the next.
            if let label = canonical(line), index + 1 < lines.count, looksLikeValue(lines[index + 1]) {
                add(label: label, value: lines[index + 1], to: &found)
                continue
            }
            // A date, long number or phone number after a label word on the same line.
            if let label = canonical(line), let value = trailingValue(in: line) {
                add(label: label, value: value, to: &found)
            }
        }
        return Array(found.prefix(8))
    }

    private static func canonical(_ label: String) -> String? {
        knownLabels.first { label.range(of: $0.pattern, options: .regularExpression) != nil }?.label
    }

    private static func looksLikeValue(_ line: String) -> Bool {
        (2...60).contains(line.count) && canonical(line) == nil && !line.hasSuffix(":")
    }

    private static func trailingValue(in line: String) -> String? {
        for pattern in [
            #"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"#, #"\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}"#,
            #"\+?\d[\d\s\-]{7,16}\d"#, #"\b(?=[A-Z0-9\-]*\d)[A-Z0-9][A-Z0-9\-]{5,}\b"#,
        ] {
            if let range = line.range(of: pattern, options: .regularExpression) { return String(line[range]) }
        }
        return nil
    }

    private static func add(label: String, value: String, to found: inout [Detail]) {
        let value = value.trimmingCharacters(in: .whitespacesAndNewlines.union(.punctuationCharacters))
        guard (1...80).contains(value.count), !found.contains(where: { $0.label == label }) else { return }
        found.append(Detail(label: label, value: value))
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
