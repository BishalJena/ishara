import SwiftUI

/// A round avatar with someone's initials, or a person glyph when there's no name to take
/// them from (a bare number, or no name saved yet).
struct InitialsAvatar: View {
    let name: String
    var color: Color = .blue
    var size: CGFloat = 44
    var foreground: Color = .white

    static func initials(_ name: String) -> String {
        guard name.first?.isLetter == true else { return "" }
        return name.split(separator: " ").prefix(2).compactMap { $0.first.map(String.init) }.joined().uppercased()
    }

    var body: some View {
        let initials = Self.initials(name)
        Circle().fill(color).frame(width: size, height: size)
            .overlay {
                if initials.isEmpty {
                    Image(systemName: "person.fill").font(.system(size: size * 0.42)).foregroundStyle(foreground)
                } else {
                    Text(initials).font(.system(size: size * 0.38, weight: .bold)).foregroundStyle(foreground)
                }
            }
            .accessibilityHidden(true)
    }
}
