/*
See the LICENSE.txt file for this sample’s licensing information.

Abstract:
An actor that generates speech from text.
*/

import AVFAudio

@MainActor
final class SpeechSynthesizer {

    private let speechSynth = AVSpeechSynthesizer()
    private var clipPlayer: AVAudioPlayer?

    func synthesizeSpeech(text: String) {
        stop()
        let utterance = AVSpeechUtterance(string: text)
        // Use an enhanced-quality voice if one exists for the current language code.
        utterance.voice = AVSpeechSynthesisVoice.speechVoices().first {
            $0.language == AVSpeechSynthesisVoice.currentLanguageCode() && $0.quality == .enhanced
        }
        // Speak the passed in text.
        speechSynth.speak(utterance)
    }

    func stop() {
        speechSynth.stopSpeaking(at: .immediate)
        clipPlayer?.stop()
        clipPlayer = nil
    }

    // External speech audio exercises the same injection preference as the control voice.
    // Source: https://developer.apple.com/documentation/avfaudio/adding-synthesized-speech-to-calls
    func play(data: Data) throws {
        stop()
        let player = try AVAudioPlayer(data: data)
        guard player.prepareToPlay(), player.play() else {
            throw PlaybackError.unavailable
        }
        clipPlayer = player
    }

    enum PlaybackError: Error { case unavailable }
}
