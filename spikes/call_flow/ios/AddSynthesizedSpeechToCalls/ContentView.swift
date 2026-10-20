/* Adapted from Apple's AAC sample. See ../LICENSE.txt. */
import SwiftUI
import Accessibility
import AVFAudio
import UniformTypeIdentifiers

struct ContentView: View {
    @Environment(\.scenePhase) private var scenePhase
    @State private var callAudio = CallAudio()
    @State private var speech = SpeechSynthesizer()
    @State private var camera = CameraCapture()
    @State private var cameraOn = false
    @State private var cameraStatus = "Preview off. No video is saved."
    @State private var addAudio = false
    @State private var requestingAudio = false
    @State private var importingAudio = false
    @State private var message: String?

    private var audioBinding: Binding<Bool> {
        Binding(get: { addAudio }, set: { value in
            requestingAudio = true
            speech.stop()
            Task {
                defer { requestingAudio = false }
                switch await callAudio.setAppAudioEnabled(value) {
                case .success(let enabled): addAudio = enabled
                case .failure(let error):
                    addAudio = false
                    switch error {
                    case .serviceDisabled: message = "Enable Settings → Accessibility → Audio & Visual → Add Audio in Calls, then return here."
                    case .permissionDenied: message = "Allow Ishara in the Add Audio in Calls settings."
                    case .unknown: message = "Audio injection could not be enabled. Try again during an active call."
                    }
                }
            }
        })
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("1 · Your call") {
                    Text("Start a WhatsApp voice call, then return here. Phone calls use the same test later.")
                    Toggle("Add speech to call", isOn: audioBinding).disabled(requestingAudio)
                    Text(callAudio.injectionAvailability.map {
                        $0 ? "System reports audio injection available." : "System reports audio injection unavailable."
                    } ?? "Waiting for a call-audio status update.").font(.caption)
                    Text("Enabled does not confirm the recipient heard it. Ask them to repeat the test sentence.").font(.caption)
                }
                Section("2 · Speech test") {
                    Text("Apple voice control. Signing is mocked; Bolna speech is still blocked.").font(.caption)
                    Button("Speak test sentence") {
                        speech.synthesizeSpeech(text: "Hello. This is the Ishara audio test. Can you hear this sentence?")
                    }
                    Button("Ask for a reply") {
                        speech.synthesizeSpeech(text: "Thank you. Please say what time is available.")
                    }
                    Button("Speak longer sentence to test Stop") {
                        speech.synthesizeSpeech(text: "Please give me a moment. I am reading your reply and preparing my response. Please wait until I finish before you continue. Thank you for waiting.")
                    }
                    Button("Stop speech", role: .destructive) { speech.stop() }
                    Button("Import external speech clip") {
                        speech.stop()
                        importingAudio = true
                    }
                }
                Section("3 · Camera coexistence") {
                    Toggle("Front camera preview", isOn: $cameraOn)
                    if cameraOn {
                        CameraPreview(source: camera.previewSource)
                            .frame(height: 230)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                    }
                    Text(cameraStatus).font(.caption)
                    Text("Preview only. No sign classifier or recording runs.").font(.caption)
                }
                Section("4 · Read the reply") {
                    Text("Enable Settings → Accessibility → Live Captions. Select iPhone Audio in the caption window, then ask the recipient to speak.")
                    Text("Captions are supplied by iOS, outside this app. Check they remain visible with the camera preview and speech enabled.").font(.caption)
                    Button("Open call-audio settings") {
                        Task {
                            do { try await AccessibilitySettings.openSettings(for: .allowAppsToAddAudioToCalls) }
                            catch { message = "Open Accessibility → Audio & Visual → Add Audio in Calls in Settings." }
                        }
                    }
                }
            }
            .navigationTitle("Ishara call check")
            .task(id: cameraOn) {
                if cameraOn {
                    let status = await camera.start()
                    if !Task.isCancelled { cameraStatus = status }
                } else {
                    await camera.stop()
                    cameraStatus = "Preview off. No video is saved."
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .background {
                    speech.stop()
                    cameraOn = false
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification)) { _ in
                speech.stop()
            }
        }
        .fileImporter(isPresented: $importingAudio, allowedContentTypes: [.wav, .mp3]) { result in
            do {
                let url = try result.get()
                let scoped = url.startAccessingSecurityScopedResource()
                defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
                guard size > 0 && size <= 16 * 1024 * 1024 else {
                    message = "Choose a WAV or MP3 smaller than 16 MB."
                    return
                }
                try speech.play(data: Data(contentsOf: url))
            } catch { message = "The clip could not be played. Choose a valid WAV or MP3." }
        }
        .alert("Test setup", isPresented: Binding(get: { message != nil }, set: { if !$0 { message = nil } })) {
            Button("OK", role: .cancel) { message = nil }
        } message: { Text(message ?? "") }
    }
}
