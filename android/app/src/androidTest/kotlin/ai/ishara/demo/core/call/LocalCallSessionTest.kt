package ai.ishara.demo.core.call

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** CallSession's real `TurnStore` in the Swift core, driven through the bridge with Kotlin playing the backend. */
@RunWith(AndroidJUnit4::class)
class LocalCallSessionTest {
    private val sessions = mutableListOf<LocalCallSession>()
    private val recorders = mutableListOf<Recorder<*>>()

    @After
    fun tearDown() {
        recorders.forEach(Recorder<*>::close)
        onMain { sessions.forEach(LocalCallSession::close) }
    }

    private fun start(state: CallState = CallState.IN_CALL): Pair<LocalCallSession, Recorder<Outgoing>> {
        val session = onMain { CallCore.startLocalSession(state) }.also { sessions += it }
        return session to Recorder(session.outgoing).also { recorders += it }
    }

    @Test
    fun startHasTheStoresInitialSnapshot() {
        val (session, _) = start(CallState.IN_CALL)

        val snapshot = session.snapshot.value
        assertEquals(CallState.IN_CALL, snapshot.state)
        assertNotNull("a live call starts its timer", snapshot.connectedAt)
        assertTrue(snapshot.currentTurnId.matches(Regex("[0-9a-f]{32}")))
        assertEquals(emptyList<Chip>(), snapshot.chips)
        assertEquals(SendingPhase.Idle, snapshot.sending)
        assertFalse(snapshot.canSend)
        assertEquals(CallState.DIALING, start(CallState.DIALING).first.snapshot.value.state)
    }

    @Test
    fun aWholeTurnGoesFromChipsToADraftToOneApproval() {
        val (session, outgoing) = start()
        val chip = Chip.recognised(Sign.HELLO)

        assertTrue(onMain { session.add(chip) })
        val turn = session.awaitSnapshot { it.chips == listOf(chip) }.currentTurnId
        assertEquals(Outgoing.Message(AppMessage.Chips(turn, listOf(Sign.HELLO))), outgoing.next())

        onMain { session.receive(ServerMessage.Draft(turn, "Hello.", DraftSource.LLM)) }
        val drafted = session.awaitSnapshot { it.draft != null }
        assertEquals(Draft("Hello.", Draft.Origin.LLM), drafted.draft)
        assertTrue(drafted.canSend)
        outgoing.assertQuiet()

        onMain { session.send() }
        assertEquals(Outgoing.Message(AppMessage.Approve(turn, "Hello.")), outgoing.next())
        val speaking = session.awaitSnapshot { it.sending is SendingPhase.Speaking }
        assertEquals(SendingPhase.Speaking(turn, "Hello."), speaking.sending)
        assertNotEquals("SEND starts a new turn", turn, speaking.currentTurnId)
        assertEquals(emptyList<Chip>(), speaking.chips)

        onMain { session.send() }
        outgoing.assertQuiet()

        onMain { session.receive(ServerMessage.Spoken(turn)) }
        val delivered = session.awaitSnapshot { it.sending == SendingPhase.Delivered }
        assertEquals(Caption.Speaker.USER, delivered.captions.last().speaker)
        assertEquals("Hello.", delivered.captions.last().text)
    }

    @Test
    fun aDraftForAnOlderTurnIsIgnored() {
        val (session, outgoing) = start()
        onMain { session.add(Chip.recognised(Sign.HELLO)) }
        val oldTurn = (outgoing.next() as Outgoing.Message).message.let { (it as AppMessage.Chips).turnId }
        onMain {
            session.clear()
            session.add(Chip.recognised(Sign.YES))
        }
        val newTurn = ((outgoing.next() as Outgoing.Message).message as AppMessage.Chips).turnId
        assertNotEquals(oldTurn, newTurn)

        onMain { session.receive(ServerMessage.Draft(oldTurn, "Hello.", DraftSource.LLM)) }
        onMain { session.receive(ServerMessage.Draft(newTurn, "Yes.", DraftSource.TEMPLATE)) }

        val drafted = session.awaitSnapshot { it.draft != null }
        assertEquals(Draft("Yes.", Draft.Origin.TEMPLATE), drafted.draft)
    }

    @Test
    fun aProposalIsApprovedWithItsOwnTurnAndText() {
        val (session, outgoing) = start()
        onMain { session.receive(ServerMessage.Proposal("p7", "Tomorrow morning works.", 3.0)) }
        session.awaitSnapshot { it.proposal != null }
        outgoing.assertQuiet()

        onMain { session.approveProposal() }

        assertEquals(Outgoing.Message(AppMessage.Approve("p7", "Tomorrow morning works.")), outgoing.next())
        session.awaitSnapshot { it.proposal == null }
    }

    @Test
    fun endDropsWhatIsQueuedThenSendsEnd() {
        val (session, outgoing) = start()

        onMain { session.end() }

        assertEquals(Outgoing.DiscardPending, outgoing.next())
        assertEquals(Outgoing.Message(AppMessage.End), outgoing.next())
        session.awaitSnapshot { it.state == CallState.ENDED }
        assertFalse("nothing is added after End", onMain { session.add(Chip.recognised(Sign.YES)) })
        assertFalse(onMain { session.say("Hello") })
    }

    @Test
    fun everyChangeProducesAFreshSnapshot() {
        val (session, _) = start()
        for (count in 1..4) {
            onMain { session.add(Chip.unsure()) }
            session.awaitSnapshot { it.chips.size == count }
        }
        onMain { session.receive(ServerMessage.Caption("City Clinic, hello.", 1.0)) }
        assertEquals("City Clinic, hello.", session.awaitSnapshot { it.captions.isNotEmpty() }.captions.single().text)
    }

    @Test
    fun anOpenQuestionIsAnsweredOnlyWithOneOfItsOptions() {
        val (session, outgoing) = start()
        onMain {
            session.receive(
                ServerMessage.Ask("a1", "4 pm?", listOf(AskOption(AskChoice.YES, "Yes, 4 pm works.")), "I'll call back.", 10.0),
            )
        }
        session.awaitSnapshot { it.openQuestion?.askId == "a1" }

        assertFalse(onMain { session.answer(AskChoice.NO) })
        assertTrue(onMain { session.answerIfAsked(Sign.YES) })
        assertEquals(Outgoing.Message(AppMessage.Answer("a1", AskChoice.YES)), outgoing.next())
    }

    @Test
    fun aLostConnectionGoesSilent() {
        val (session, outgoing) = start()
        onMain { session.add(Chip.recognised(Sign.HELLO)) }
        outgoing.next()

        onMain { session.connectionLost() }

        assertEquals(Outgoing.DiscardPending, outgoing.next())
        val silent = session.awaitSnapshot { it.state == CallState.ERROR }
        assertEquals("Nothing will be sent", silent.notice)
        assertEquals(emptyList<Chip>(), silent.chips)
    }

    @Test
    fun commandsOffTheMainThreadThrow() {
        val (session, _) = start()

        assertThrows(IllegalStateException::class.java) { session.add(Chip.recognised(Sign.HELLO)) }
    }

    @Test
    fun aClosedSessionTakesNoCommands() {
        val (session, _) = start()
        onMain { session.close() }

        assertThrows(IllegalStateException::class.java) { onMain { session.send() } }
    }
}
