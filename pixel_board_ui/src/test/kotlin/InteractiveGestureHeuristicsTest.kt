package com.pixelboard

import java.awt.Frame
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class InteractiveGestureHeuristicsTest {
    @Test
    fun interactivePointerUsesRawScreenPositionWithoutDeadband() {
        val stabilized = stabilizeInteractiveScreenPosition(
            previousX = 1000,
            previousY = 500,
            rawX = 1006,
            rawY = 503,
        )

        assertEquals(1006 to 503, stabilized)
    }

    @Test
    fun singleConfirmedVisibleFrameCanQualifyAsATap() {
        assertTrue(
            isTapFrameConfirmationSatisfied(
                seenFrames = 1,
                hoverAnchorFrames = 1,
            ),
        )
    }

    @Test
    fun doubleTapDetectedWhenWithinRadius() {
        assertTrue(
            isWithinDoubleTapRadius(
                firstScreenX = 820,
                firstScreenY = 460,
                secondScreenX = 835,
                secondScreenY = 470,
            ),
        )
    }

    @Test
    fun doubleTapNotDetectedWhenOutsideRadius() {
        assertFalse(
            isWithinDoubleTapRadius(
                firstScreenX = 820,
                firstScreenY = 460,
                secondScreenX = 860,
                secondScreenY = 460,
            ),
        )
    }

    @Test
    fun doubleTapDetectedAtExactRadius() {
        // Distance = 30.0 exactly (18^2 + 24^2 = 900, sqrt = 30)
        assertTrue(
            isWithinDoubleTapRadius(
                firstScreenX = 100,
                firstScreenY = 100,
                secondScreenX = 118,
                secondScreenY = 124,
            ),
        )
    }

    @Test
    fun doubleTapNotDetectedJustOutsideRadius() {
        // Distance = ~31.1 (just outside 30)
        assertFalse(
            isWithinDoubleTapRadius(
                firstScreenX = 100,
                firstScreenY = 100,
                secondScreenX = 120,
                secondScreenY = 124,
            ),
        )
    }

    @Test
    fun pointerVelocityReflectsMeasuredMotion() {
        val velocity = computeInteractivePointerVelocity(
            previousMeasuredX = 100,
            previousMeasuredY = 200,
            previousMeasuredAtMs = 1_000L,
            currentMeasuredX = 120,
            currentMeasuredY = 230,
            currentMeasuredAtMs = 1_050L,
        )

        assertEquals(0.4, velocity.first, 0.001)
        assertEquals(0.6, velocity.second, 0.001)
    }

    @Test
    fun pointerPredictionUsesCpuTimeButCapsHowFarAheadItLeads() {
        val predicted = predictInteractiveScreenPosition(
            measuredX = 500,
            measuredY = 300,
            velocityXPxPerMs = 0.5,
            velocityYPxPerMs = -0.2,
            elapsedSinceMeasurementMs = 120L,
        )

        assertEquals(500 to 300, predicted)
    }

    @Test
    fun pixelBoardWindowSuppressionRequiresForegroundWindow() {
        assertFalse(
            shouldUsePixelBoardWindowSuppression(
                title = "PixelBoard",
                isShowing = true,
                extendedState = Frame.NORMAL,
                isActive = false,
            ),
        )
    }

    @Test
    fun pixelBoardWindowSuppressionIgnoresIconifiedWindow() {
        assertFalse(
            shouldUsePixelBoardWindowSuppression(
                title = "PixelBoard",
                isShowing = true,
                extendedState = Frame.ICONIFIED,
                isActive = true,
            ),
        )
    }
}
