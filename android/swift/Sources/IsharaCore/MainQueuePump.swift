import CAndroidBridge

/// On Android nothing runs a CFRunLoop or `dispatchMain()`, so work sent to
/// `DispatchQueue.main` (and every `@MainActor` job, such as TurnStore's) would never run.
/// This hands libdispatch's main-queue eventfd to the Android main thread's ALooper,
/// which drains the queue whenever it is signalled, the way CFRunLoop does on Linux.
///
/// libdispatch binds the main queue to the thread that loaded it, so the library must be
/// loaded and this installed from the Android main thread.
enum MainQueuePump {
    nonisolated(unsafe) private static var installed = false

    static func install() throws(PumpError) {
        guard gettid() == getpid() else { throw .notOnMainThread }
        guard !installed else { return }
        guard let looper = ALooper_forThread() else { throw .noLooper }
        let fd = _dispatch_get_main_queue_handle_4CF()
        guard ALooper_addFd(looper, fd, Int32(ALOOPER_POLL_CALLBACK), Int32(ALOOPER_EVENT_INPUT), drainMainQueue, nil) == 1
        else { throw .addFdFailed }
        ALooper_acquire(looper)
        installed = true
    }

    enum PumpError: Error, CustomStringConvertible {
        case notOnMainThread, noLooper, addFdFailed

        var description: String {
            switch self {
            case .notOnMainThread: "the main-queue pump must be installed from the Android main thread"
            case .noLooper: "the main thread has no ALooper"
            case .addFdFailed: "ALooper_addFd failed for the main-queue eventfd"
            }
        }
    }
}

private let drainMainQueue: ALooper_callbackFunc = { fd, _, _ in
    // The eventfd is non-blocking and level-triggered: acknowledge it before draining.
    var count: eventfd_t = 0
    _ = eventfd_read(fd, &count)
    _dispatch_main_queue_callback_4CF(nil)
    return 1
}
