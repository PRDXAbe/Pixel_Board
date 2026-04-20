package com.pixelboard

import java.awt.AWTError
import java.awt.AWTException
import java.awt.GraphicsEnvironment
import java.awt.Rectangle
import java.awt.Robot
import java.awt.Toolkit
import java.awt.event.InputEvent
import java.awt.image.BufferedImage

data class DisplayTarget(
    val id: String,
    val name: String,
    val x: Int,
    val y: Int,
    val width: Int,
    val height: Int,
    val isPrimary: Boolean,
) {
    val bounds: Rectangle
        get() = Rectangle(x, y, width, height)

    val label: String
        get() = buildString {
            append(name)
            if (isPrimary) append(" · Primary")
            append(" · ")
            append("${width}x${height}")
            append(" @ ")
            append("${x},${y}")
        }
}

data class DesktopInjectionStatus(
    val available: Boolean,
    val message: String,
)

interface DesktopInputController {
    val displays: List<DisplayTarget>
    val status: DesktopInjectionStatus

    fun move(x: Int, y: Int)
    fun click(x: Int, y: Int)
    fun doubleClick(x: Int, y: Int)
    fun mouseDown()
    fun mouseUp()
    fun releaseAll()
    fun capture(display: DisplayTarget): BufferedImage?
}

private class DisabledDesktopInputController(
    override val displays: List<DisplayTarget>,
    override val status: DesktopInjectionStatus,
) : DesktopInputController {
    override fun move(x: Int, y: Int) = Unit
    override fun click(x: Int, y: Int) = Unit
    override fun doubleClick(x: Int, y: Int) = Unit
    override fun mouseDown() = Unit
    override fun mouseUp() = Unit
    override fun releaseAll() = Unit
    override fun capture(display: DisplayTarget): BufferedImage? = null
}

private class RobotDesktopInputController(
    override val displays: List<DisplayTarget>,
    override val status: DesktopInjectionStatus,
    private val robot: Robot,
) : DesktopInputController {
    private var buttonDown = false

    override fun move(x: Int, y: Int) {
        robot.mouseMove(x, y)
        Toolkit.getDefaultToolkit().sync()
    }

    override fun click(x: Int, y: Int) {
        move(x, y)
        robot.delay(DESKTOP_CLICK_SETTLE_MS)
        robot.mousePress(InputEvent.BUTTON1_DOWN_MASK)
        buttonDown = true
        Toolkit.getDefaultToolkit().sync()
        robot.delay(DESKTOP_CLICK_HOLD_MS)
        robot.mouseRelease(InputEvent.BUTTON1_DOWN_MASK)
        buttonDown = false
        Toolkit.getDefaultToolkit().sync()
        robot.delay(DESKTOP_CLICK_RELEASE_SETTLE_MS)
    }

    override fun doubleClick(x: Int, y: Int) {
        click(x, y)
        robot.delay(DESKTOP_DOUBLE_CLICK_INTERVAL_MS)
        click(x, y)
    }

    override fun mouseDown() {
        if (buttonDown) return
        robot.mousePress(InputEvent.BUTTON1_DOWN_MASK)
        buttonDown = true
        Toolkit.getDefaultToolkit().sync()
    }

    override fun mouseUp() {
        if (!buttonDown) return
        robot.mouseRelease(InputEvent.BUTTON1_DOWN_MASK)
        buttonDown = false
        Toolkit.getDefaultToolkit().sync()
    }

    override fun releaseAll() {
        mouseUp()
    }

    override fun capture(display: DisplayTarget): BufferedImage? =
        runCatching { robot.createScreenCapture(display.bounds) }.getOrNull()
}

fun probeAvailableDisplays(): List<DisplayTarget> {
    if (GraphicsEnvironment.isHeadless()) {
        return emptyList()
    }
    return try {
        val graphicsEnvironment = GraphicsEnvironment.getLocalGraphicsEnvironment()
        val primaryBounds = graphicsEnvironment.defaultScreenDevice.defaultConfiguration.bounds
        graphicsEnvironment.screenDevices.mapIndexed { index, device ->
            val bounds = device.defaultConfiguration.bounds
            DisplayTarget(
                id = device.getIDstring(),
                name = "Display ${index + 1}",
                x = bounds.x,
                y = bounds.y,
                width = bounds.width,
                height = bounds.height,
                isPrimary = bounds == primaryBounds,
            )
        }.sortedWith(compareByDescending<DisplayTarget> { it.isPrimary }.thenBy { it.x }.thenBy { it.y })
    } catch (_: AWTError) {
        emptyList()
    } catch (_: Throwable) {
        emptyList()
    }
}

fun createDesktopInputController(): DesktopInputController {
    return try {
        if (GraphicsEnvironment.isHeadless()) {
            return DisabledDesktopInputController(
                displays = emptyList(),
                status = DesktopInjectionStatus(
                    available = false,
                    message = "Desktop interaction is unavailable in a headless session.",
                ),
            )
        }

        val displays = probeAvailableDisplays()
        if (displays.isEmpty()) {
            return DisabledDesktopInputController(
                displays = emptyList(),
                status = DesktopInjectionStatus(
                    available = false,
                    message = "No displays were detected for projected interaction.",
                ),
            )
        }

        val sessionType = System.getenv("XDG_SESSION_TYPE")?.lowercase()
        if (sessionType == "wayland") {
            return DisabledDesktopInputController(
                displays = displays,
                status = DesktopInjectionStatus(
                    available = false,
                    message = "Projected interaction currently supports X11 sessions. Current session: Wayland.",
                ),
            )
        }

        val robot = Robot()
        robot.setAutoWaitForIdle(false)
        RobotDesktopInputController(
            displays = displays,
            status = DesktopInjectionStatus(
                available = true,
                message = "Projected interaction is ready on ${displays.size} display${if (displays.size == 1) "" else "s"}.",
            ),
            robot = robot,
        )
    } catch (error: AWTError) {
        DisabledDesktopInputController(
            displays = emptyList(),
            status = DesktopInjectionStatus(
                available = false,
                message = "Could not access the X11 desktop for projected interaction: ${error.message ?: "unknown error"}.",
            ),
        )
    } catch (error: AWTException) {
        DisabledDesktopInputController(
            displays = emptyList(),
            status = DesktopInjectionStatus(
                available = false,
                message = "Could not create a desktop input controller for this session: ${error.message ?: "unknown error"}.",
            ),
        )
    }
}

private const val DESKTOP_CLICK_SETTLE_MS = 35
private const val DESKTOP_CLICK_HOLD_MS = 55
private const val DESKTOP_CLICK_RELEASE_SETTLE_MS = 25
private const val DESKTOP_DOUBLE_CLICK_INTERVAL_MS = 90
