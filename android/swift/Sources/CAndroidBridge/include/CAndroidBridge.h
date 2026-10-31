#pragma once

#include <android/log.h>
#include <android/looper.h>
#include <jni.h>
#include <sys/eventfd.h>
#include <unistd.h>

// libdispatch SPI (exported by libdispatch.so, used by CoreFoundation's run loop):
// the eventfd that is signalled when work lands on the main queue, and the drain call.
int _dispatch_get_main_queue_handle_4CF(void);
void _dispatch_main_queue_callback_4CF(void *_Nullable msg);
