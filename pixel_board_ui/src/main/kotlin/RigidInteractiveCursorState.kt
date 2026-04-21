package com.pixelboard

import kotlin.math.hypot
import kotlin.math.roundToInt

internal const val RIGID_CURSOR_BREAKOUT_PX = 4.0
internal const val RIGID_CURSOR_BREAKOUT_CONFIRM_FRAMES = 2
internal const val RIGID_CURSOR_RELOCK_PX = 4.0
internal const val RIGID_CURSOR_RELOCK_FRAMES = 2
internal const val RIGID_CURSOR_LOST_HOLD_FRAMES = 2
private const val RIGID_CURSOR_CATCH_UP_ALPHA = 0.7
private const val RIGID_CURSOR_MOVING_ALPHA = 0.65

enum class CursorPhase {
    LOCKED_HOVER,
    CATCHING_UP,
    MOVING_RIGID,
    LOST_HOLD,
}

data class RigidInteractiveCursorState(
    val touchId: Int,
    val visibleScreenX: Int,
    val visibleScreenY: Int,
    val lockAnchorX: Int,
    val lockAnchorY: Int,
    val phase: CursorPhase,
    val missingFrames: Int,
    val breakoutFrames: Int,
    val settleFrames: Int,
    val lastTimestampMs: Long,
) {
    fun visiblePosition(): Pair<Int, Int> = visibleScreenX to visibleScreenY

    fun visiblePositionOrNull(): Pair<Int, Int>? =
        if (missingFrames > RIGID_CURSOR_LOST_HOLD_FRAMES) null else visiblePosition()

    fun advanceVisibleTouch(
        touchId: Int,
        rawScreenX: Int,
        rawScreenY: Int,
        timestampMs: Long,
    ): RigidInteractiveCursorState {
        if (touchId != this.touchId) {
            return locked(
                touchId = touchId,
                screenX = rawScreenX,
                screenY = rawScreenY,
                timestampMs = timestampMs,
            )
        }

        val breakoutDistance = hypot(
            (rawScreenX - lockAnchorX).toDouble(),
            (rawScreenY - lockAnchorY).toDouble(),
        )
        return when (phase) {
            CursorPhase.LOCKED_HOVER, CursorPhase.LOST_HOLD -> {
                if (breakoutDistance <= RIGID_CURSOR_BREAKOUT_PX) {
                    copy(
                        phase = CursorPhase.LOCKED_HOVER,
                        missingFrames = 0,
                        breakoutFrames = 0,
                        settleFrames = 0,
                        lastTimestampMs = timestampMs,
                    )
                } else {
                    val nextBreakoutFrames = breakoutFrames + 1
                    if (nextBreakoutFrames < RIGID_CURSOR_BREAKOUT_CONFIRM_FRAMES) {
                        copy(
                            phase = CursorPhase.LOCKED_HOVER,
                            missingFrames = 0,
                            breakoutFrames = nextBreakoutFrames,
                            settleFrames = 0,
                            lastTimestampMs = timestampMs,
                        )
                    } else {
                        copy(
                            visibleScreenX = blendScreen(visibleScreenX, rawScreenX, RIGID_CURSOR_CATCH_UP_ALPHA),
                            visibleScreenY = blendScreen(visibleScreenY, rawScreenY, RIGID_CURSOR_CATCH_UP_ALPHA),
                            lockAnchorX = rawScreenX,
                            lockAnchorY = rawScreenY,
                            phase = CursorPhase.CATCHING_UP,
                            missingFrames = 0,
                            breakoutFrames = 0,
                            settleFrames = 0,
                            lastTimestampMs = timestampMs,
                        )
                    }
                }
            }

            CursorPhase.CATCHING_UP, CursorPhase.MOVING_RIGID -> {
                val nextVisibleX = blendScreen(visibleScreenX, rawScreenX, RIGID_CURSOR_MOVING_ALPHA)
                val nextVisibleY = blendScreen(visibleScreenY, rawScreenY, RIGID_CURSOR_MOVING_ALPHA)
                val nextRelockDistance = hypot(
                    (rawScreenX - nextVisibleX).toDouble(),
                    (rawScreenY - nextVisibleY).toDouble(),
                )
                val nextSettleFrames = if (nextRelockDistance <= RIGID_CURSOR_RELOCK_PX) {
                    settleFrames + 1
                } else {
                    0
                }
                if (nextSettleFrames >= RIGID_CURSOR_RELOCK_FRAMES) {
                    copy(
                        visibleScreenX = rawScreenX,
                        visibleScreenY = rawScreenY,
                        lockAnchorX = rawScreenX,
                        lockAnchorY = rawScreenY,
                        phase = CursorPhase.LOCKED_HOVER,
                        missingFrames = 0,
                        breakoutFrames = 0,
                        settleFrames = 0,
                        lastTimestampMs = timestampMs,
                    )
                } else {
                    copy(
                        visibleScreenX = nextVisibleX,
                        visibleScreenY = nextVisibleY,
                        lockAnchorX = rawScreenX,
                        lockAnchorY = rawScreenY,
                        phase = CursorPhase.MOVING_RIGID,
                        missingFrames = 0,
                        breakoutFrames = 0,
                        settleFrames = nextSettleFrames,
                        lastTimestampMs = timestampMs,
                    )
                }
            }
        }
    }

    fun advanceTouchLoss(timestampMs: Long): RigidInteractiveCursorState =
        copy(
            phase = CursorPhase.LOST_HOLD,
            missingFrames = missingFrames + 1,
            breakoutFrames = 0,
            settleFrames = 0,
            lastTimestampMs = timestampMs,
        )

    companion object {
        fun locked(
            touchId: Int,
            screenX: Int,
            screenY: Int,
            timestampMs: Long,
        ) = RigidInteractiveCursorState(
            touchId = touchId,
            visibleScreenX = screenX,
            visibleScreenY = screenY,
            lockAnchorX = screenX,
            lockAnchorY = screenY,
            phase = CursorPhase.LOCKED_HOVER,
            missingFrames = 0,
            breakoutFrames = 0,
            settleFrames = 0,
            lastTimestampMs = timestampMs,
        )
    }
}

private fun blendScreen(current: Int, target: Int, alpha: Double): Int =
    ((current * (1.0 - alpha)) + (target * alpha)).roundToInt()
