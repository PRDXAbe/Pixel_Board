package com.pixelboard

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ── JSON wire types ───────────────────────────────────────────────────────────

@Serializable
data class TouchPointJson(
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
)

// ── UI types ──────────────────────────────────────────────────────────────────

data class TouchPoint(
    val px: Int,
    val py: Int,
    val mx: Float,
    val my: Float,
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
)

/**
 * Mutable board config — edited by the user in the control panel.
 * Mirrors the entries in board_config.json that the UI can modify.
 */
data class BoardConfig(
    val widthMm:  Int   = 1000,
    val heightMm: Int   = 500,
)

data class AppUiState(
    val isDriverRunning: Boolean     = false,
    val isConnected:     Boolean     = false,
    val frame:           BoardFrame  = BoardFrame(),
    val boardConfig:     BoardConfig = BoardConfig(),
    val errorMessage:    String?     = null,
)

fun BoardFrameJson.toUiFrame() = BoardFrame(
    scanPts      = scanPts.mapNotNull  { if (it.size >= 2) it[0] to it[1] else null },
    boardPts     = boardPts.mapNotNull { if (it.size >= 2) it[0] to it[1] else null },
    touches      = touches.map { TouchPoint(it.px, it.py, it.mx, it.my) },
    scanCount    = scanCount,
    rateHz       = rateHz,
    boardMinX    = boardMinX,
    boardMaxX    = boardMaxX,
    boardMinY    = boardMinY,
    boardMaxY    = boardMaxY,
    boardWidthMm  = boardWidthMm,
    boardHeightMm = boardHeightMm,
)
