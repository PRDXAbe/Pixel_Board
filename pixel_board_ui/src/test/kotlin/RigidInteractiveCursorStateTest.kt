package com.pixelboard

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class RigidInteractiveCursorStateTest {
    @Test
    fun lockedHoverIgnoresSubThresholdRedPointWobble() {
        var state = RigidInteractiveCursorState.locked(
            touchId = 7,
            screenX = 400,
            screenY = 300,
            timestampMs = 1_000L,
        )

        state = state.advanceVisibleTouch(
            touchId = 7,
            rawScreenX = 403,
            rawScreenY = 302,
            timestampMs = 1_050L,
        )

        assertEquals(400 to 300, state.visiblePosition())
    }

    @Test
    fun breakoutStartsShortCatchUpWhenThresholdIsExceeded() {
        var state = RigidInteractiveCursorState.locked(
            touchId = 7,
            screenX = 400,
            screenY = 300,
            timestampMs = 1_000L,
        )

        state = state.advanceVisibleTouch(
            touchId = 7,
            rawScreenX = 405,
            rawScreenY = 300,
            timestampMs = 1_050L,
        )

        assertEquals(CursorPhase.LOCKED_HOVER, state.phase)
        assertEquals(400 to 300, state.visiblePosition())
    }

    @Test
    fun repeatedBreakoutMotionStartsShortCatchUp() {
        var state = RigidInteractiveCursorState.locked(
            touchId = 7,
            screenX = 400,
            screenY = 300,
            timestampMs = 1_000L,
        )

        state = state.advanceVisibleTouch(
            touchId = 7,
            rawScreenX = 405,
            rawScreenY = 300,
            timestampMs = 1_050L,
        )
        state = state.advanceVisibleTouch(
            touchId = 7,
            rawScreenX = 406,
            rawScreenY = 301,
            timestampMs = 1_100L,
        )

        assertEquals(CursorPhase.CATCHING_UP, state.phase)
    }

    @Test
    fun singleBreakoutSpikeDoesNotCauseVisibleDrift() {
        var state = RigidInteractiveCursorState.locked(
            touchId = 7,
            screenX = 400,
            screenY = 300,
            timestampMs = 1_000L,
        )

        state = state.advanceVisibleTouch(
            touchId = 7,
            rawScreenX = 406,
            rawScreenY = 300,
            timestampMs = 1_050L,
        )
        state = state.advanceVisibleTouch(
            touchId = 7,
            rawScreenX = 401,
            rawScreenY = 300,
            timestampMs = 1_100L,
        )

        assertEquals(CursorPhase.LOCKED_HOVER, state.phase)
        assertEquals(400 to 300, state.visiblePosition())
    }

    @Test
    fun briefTouchLossFreezesInPlace() {
        var state = RigidInteractiveCursorState.locked(
            touchId = 7,
            screenX = 400,
            screenY = 300,
            timestampMs = 1_000L,
        )

        state = state.advanceTouchLoss(timestampMs = 1_100L)

        assertEquals(400 to 300, state.visiblePosition())
    }

    @Test
    fun expiredTouchLossReleasesCursor() {
        var state = RigidInteractiveCursorState.locked(
            touchId = 7,
            screenX = 400,
            screenY = 300,
            timestampMs = 1_000L,
        )

        state = state.advanceTouchLoss(timestampMs = 1_300L)
        state = state.advanceTouchLoss(timestampMs = 1_400L)
        state = state.advanceTouchLoss(timestampMs = 1_500L)

        assertNull(state.visiblePositionOrNull())
    }
}
