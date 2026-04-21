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
    fun syntheticDoubleClickDetectedWhenSecondTapIsNearAndRecent() {
        assertTrue(
            shouldTriggerSyntheticDoubleClick(
                previousClickAtMs = 1_000L,
                firstScreenX = 820,
                firstScreenY = 460,
                currentClickAtMs = 1_700L,
                secondScreenX = 826,
                secondScreenY = 468,
            ),
        )
    }

    @Test
    fun syntheticDoubleClickNotDetectedWhenOutsideThirtyPixelRadius() {
        assertFalse(
            shouldTriggerSyntheticDoubleClick(
                previousClickAtMs = 1_000L,
                firstScreenX = 820,
                firstScreenY = 460,
                currentClickAtMs = 1_700L,
                secondScreenX = 851,
                secondScreenY = 460,
            ),
        )
    }

    @Test
    fun syntheticDoubleClickDetectedAtExactRadius() {
        // Distance = 30.0 exactly (18^2 + 24^2 = 900, sqrt = 30)
        assertTrue(
            shouldTriggerSyntheticDoubleClick(
                previousClickAtMs = 1_000L,
                firstScreenX = 100,
                firstScreenY = 100,
                currentClickAtMs = 1_900L,
                secondScreenX = 118,
                secondScreenY = 124,
            ),
        )
    }

    @Test
    fun syntheticDoubleClickNotDetectedWhenWindowExpires() {
        assertFalse(
            shouldTriggerSyntheticDoubleClick(
                previousClickAtMs = 1_000L,
                firstScreenX = 100,
                firstScreenY = 100,
                currentClickAtMs = 6_100L,
                secondScreenX = 118,
                secondScreenY = 124,
            ),
        )
    }

    @Test
    fun secondNearbyTapBecomesSyntheticDoubleClickAtFirstAnchor() {
        val decision = decideTapReleaseAction(
            previousClickAtMs = 1_000L,
            previousClickScreenX = 820,
            previousClickScreenY = 460,
            currentClickAtMs = 1_700L,
            currentClickScreenX = 826,
            currentClickScreenY = 468,
        )

        assertEquals(TapReleaseAction.SYNTHETIC_DOUBLE_CLICK, decision.action)
        assertEquals(820, decision.targetScreenX)
        assertEquals(460, decision.targetScreenY)
    }

    @Test
    fun firstTapReleaseRemainsSingleClickAtCurrentPoint() {
        val decision = decideTapReleaseAction(
            previousClickAtMs = 0L,
            previousClickScreenX = 0,
            previousClickScreenY = 0,
            currentClickAtMs = 1_700L,
            currentClickScreenX = 826,
            currentClickScreenY = 468,
        )

        assertEquals(TapReleaseAction.SINGLE_CLICK, decision.action)
        assertEquals(826, decision.targetScreenX)
        assertEquals(468, decision.targetScreenY)
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
