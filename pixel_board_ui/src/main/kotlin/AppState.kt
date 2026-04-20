package com.pixelboard

import androidx.compose.ui.graphics.ImageBitmap
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ── LiDAR model selection ─────────────────────────────────────────────────────

enum class LidarModel {
    LD19,   // ldlidar_stl_ros2 · 230400 baud
    A1_M8;  // sllidar_ros2     · 115200 baud

    val displayName get() = when (this) {
        LD19  -> "LD19"
        A1_M8 -> "A1-M8"
    }

    val baudRate get() = when (this) {
        LD19  -> 230400
        A1_M8 -> 115200
    }
}

enum class MountMode(
    val configValue: String,
    val displayName: String,
    val uiSelectable: Boolean = true,
) {
    SIDE_EDGE("side_edge", "Side Edge"),
    BOTTOM_CENTER("bottom_center", "Bottom Center"),
    LEFT_CENTER("left_center", "Left Center", uiSelectable = false),
    RIGHT_CENTER("right_center", "Right Center", uiSelectable = false),
    TOP_CENTER("top_center", "Top Center", uiSelectable = false);

    companion object {
        fun fromConfigValue(value: String?): MountMode =
            entries.firstOrNull { it.configValue.equals(value, ignoreCase = true) } ?: SIDE_EDGE
    }
}

// ── JSON wire types ───────────────────────────────────────────────────────────

@Serializable
data class TouchPointJson(
    val id: Int = 0,
    val px: Int,
    val py: Int,
    val mx: Float,
    val my: Float,
)

@Serializable
data class BoardFrameJson(
    @SerialName("scan_pts")      val scanPts:      List<List<Float>> = emptyList(),
    @SerialName("board_pts")     val boardPts:     List<List<Float>> = emptyList(),
    val touches:                  List<TouchPointJson>               = emptyList(),
    @SerialName("scan_count")    val scanCount:    Int               = 0,
    @SerialName("rate_hz")       val rateHz:       Float             = 0f,
    @SerialName("board_min_x")   val boardMinX:    Float             = 0.05f,
    @SerialName("board_max_x")   val boardMaxX:    Float             = 1.05f,
    @SerialName("board_min_y")   val boardMinY:    Float             = -0.25f,
    @SerialName("board_max_y")   val boardMaxY:    Float             = 0.25f,
    @SerialName("board_width_mm")  val boardWidthMm:  Int            = 1000,
    @SerialName("board_height_mm") val boardHeightMm: Int            = 500,
    @SerialName("mount_mode")    val mountMode:    String            = "side_edge",
)

// ── UI types ──────────────────────────────────────────────────────────────────

data class TouchPoint(
    val id: Int,
    val px: Int,
    val py: Int,
    val mx: Float,
    val my: Float,
)

@Serializable
data class RunTouchSample(
    val touchId: Int,
    val elapsedMs: Long,
    val scanCount: Int,
    val rateHz: Float,
    val px: Int,
    val py: Int,
    val mx: Float,
    val my: Float,
)

@Serializable
data class RunCaptureExport(
    val startedAt: String,
    val savedAt: String,
    val lidarModel: String,
    val boardWidthMm: Int,
    val boardHeightMm: Int,
    val mountMode: String,
    val sampleCount: Int,
    val samples: List<RunTouchSample>,
)

data class BoardFrame(
    val scanPts:      List<Pair<Float, Float>> = emptyList(),
    val boardPts:     List<Pair<Float, Float>> = emptyList(),
    val touches:      List<TouchPoint>         = emptyList(),
    val scanCount:    Int                      = 0,
    val rateHz:       Float                    = 0f,
    val boardMinX:    Float                    = 0.05f,
    val boardMaxX:    Float                    = 1.05f,
    val boardMinY:    Float                    = -0.25f,
    val boardMaxY:    Float                    = 0.25f,
    val boardWidthMm:  Int                     = 1000,
    val boardHeightMm: Int                     = 500,
    val mountMode:    String                   = "side_edge",
)

data class BoardGeometry(
    val minX: Float = 0.05f,
    val maxX: Float = 1.05f,
    val minY: Float = -0.25f,
    val maxY: Float = 0.25f,
)

/**
 * Mutable board config — edited by the user in the control panel.
 * Mirrors the entries in board_config.json that the UI can modify.
 */
data class BoardConfig(
    val widthMm:      Int           = 1000,
    val heightMm:     Int           = 500,
    val lidarModel:   LidarModel    = LidarModel.LD19,
    val mountModeKey: String        = MountMode.SIDE_EDGE.configValue,
    val standardScreenWidthPx: Int? = null,
    val standardScreenHeightPx: Int? = null,
    val geometry:     BoardGeometry = BoardGeometry(),
) {
    val mountMode: MountMode
        get() = MountMode.fromConfigValue(mountModeKey)
}

data class AppUiState(
    val isDriverRunning: Boolean          = false,
    val isConnected:     Boolean          = false,
    val frame:           BoardFrame       = BoardFrame(),
    val boardConfig:     BoardConfig      = BoardConfig(),
    val availableDisplays: List<DisplayTarget> = emptyList(),
    val selectedDisplayId: String?        = null,
    val interactiveModeEnabled: Boolean   = false,
    val desktopInjectionAvailable: Boolean = false,
    val desktopInjectionMessage: String?  = null,
    val activeInteractiveTouchId: Int?    = null,
    val screenPreview: ImageBitmap?       = null,
    val runCaptureCount: Int              = 0,
    val lastSavedRunPath: String?         = null,
    val errorMessage:    String?          = null,
)

fun BoardFrameJson.toUiFrame() = BoardFrame(
    scanPts      = scanPts.mapNotNull  { if (it.size >= 2) it[0] to it[1] else null },
    boardPts     = boardPts.mapNotNull { if (it.size >= 2) it[0] to it[1] else null },
    touches      = touches.map { TouchPoint(it.id, it.px, it.py, it.mx, it.my) },
    scanCount    = scanCount,
    rateHz       = rateHz,
    boardMinX    = boardMinX,
    boardMaxX    = boardMaxX,
    boardMinY    = boardMinY,
    boardMaxY    = boardMaxY,
    boardWidthMm  = boardWidthMm,
    boardHeightMm = boardHeightMm,
    mountMode    = mountMode,
)
