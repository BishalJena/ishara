package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.TimedFrame
import kotlinx.coroutines.channels.ReceiveChannel
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** Saved clips replayed one after another on one forward-moving clock. Mirrors `ClipFeed` in FrameFeed.swift. */
class ClipFeedTest {
    /** Every clip is three frames 1/30 s apart; `broken` fails after its first frame. */
    private val decoder = ClipDecoder { clip, onFrame ->
        for (index in 0 until 3) {
            if (clip.name == "broken" && index == 1) throw IllegalStateException("decoder error")
            onFrame(TimedFrame(index / 30.0))
        }
    }

    private fun clip(name: String) = ReplayClip(name) { error("the scripted decoder never opens clips") }

    private fun TestScope.feed(vararg names: String) =
        ClipFeed(names.map(::clip), this, decoder, realTime = false, playerDispatcher = StandardTestDispatcher(testScheduler), log = {})

    /** Frames as their millisecond timestamps, holds as they are; collected as the player sends them. */
    private fun TestScope.collected(items: ReceiveChannel<FeedItem>): MutableList<Any> {
        val seen = mutableListOf<Any>()
        backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) {
            for (item in items) seen += if (item is FeedItem.Frame) Math.round(item.frame.timestamp * 1000) else item
        }
        return seen
    }

    @Test
    fun restPlaysFirstAndIsNotAReplayOption() = runTest {
        val feed = feed("wait_01", "rest", "hello_01")

        assertEquals(listOf("hello_01", "wait_01"), feed.replayOptions)
        val items = collected(feed.items())
        advanceUntilIdle()

        assertEquals(listOf(0L, 33L, 67L, FeedItem.Hold(0.8)), items)
        assertNull("saved videos have no live picture", feed.camera)
        feed.stop()
    }

    @Test
    fun eachClipStartsAfterTheHoldSoTimeOnlyMovesForward() = runTest {
        val feed = feed("rest", "hello_01")
        val items = collected(feed.items())
        advanceUntilIdle()

        feed.replay("hello_01")
        feed.replay("hello_01")
        advanceUntilIdle()

        // rest ended at 67 ms; + 0.8 s hold + one frame = 900 ms.
        assertEquals(
            listOf(0L, 33L, 67L, FeedItem.Hold(0.8), 900L, 933L, 967L, FeedItem.Hold(0.8), 1800L, 1833L, 1867L, FeedItem.Hold(0.8)),
            items,
        )
        feed.stop()
    }

    @Test
    fun unknownReplayIsIgnored() = runTest {
        val feed = feed("hello_01")
        val items = collected(feed.items())

        feed.replay("banana")
        advanceUntilIdle()

        assertEquals(emptyList<Any>(), items)
        feed.stop()
    }

    @Test
    fun aClipThatFailsStillEndsWithTheHold() = runTest {
        val feed = feed("broken", "hello_01")
        val items = collected(feed.items())

        feed.replay("broken")
        feed.replay("hello_01")
        advanceUntilIdle()

        assertEquals(listOf(0L, FeedItem.Hold(0.8), 833L, 867L, 900L, FeedItem.Hold(0.8)), items)
        feed.stop()
    }

    @Test
    fun stopEndsTheItems() = runTest {
        val feed = feed("rest")
        val items = feed.items()

        feed.stop()
        advanceUntilIdle()

        assertTrue(items.isClosedForReceive)
    }
}
