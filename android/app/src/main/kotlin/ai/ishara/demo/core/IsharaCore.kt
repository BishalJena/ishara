package ai.ishara.demo.core

/** Receives JSON events from the Swift core. Called on the thread that emitted the event. */
fun interface CoreEventListener {
    fun onEvent(json: String)
}

/** The Swift core (`libIsharaCore.so`, built from `android/swift`). Commands and results cross as JSON. */
object IsharaCore {
    init {
        System.loadLibrary("IsharaCore")
    }

    /**
     * Lets the Android main looper run Swift's main queue (and so `@MainActor` code).
     * Must be the first use of this object, on the main thread: libdispatch binds its
     * main queue to the thread that loads the library.
     */
    external fun installMainQueuePump()

    /** The single event listener; [CoreEvents] owns it and routes events by their `type`. */
    external fun setListener(listener: CoreEventListener?)

    external fun version(): String

    /** Hops to Swift's main actor and emits `{"type":"echo","echo": message, "onMainThread": Boolean}`. */
    external fun echoOnMain(message: String)

    /** Runs RecognitionCore's open-set matcher; throws IllegalArgumentException for invalid input. */
    external fun matchLogits(bundleJson: String, logitsJson: String, qualityJson: String): String

}
