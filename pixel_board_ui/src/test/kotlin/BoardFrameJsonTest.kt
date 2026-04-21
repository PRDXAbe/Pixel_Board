package com.pixelboard

import kotlinx.serialization.json.Json
import kotlin.test.Test
import kotlin.test.assertEquals

class BoardFrameJsonTest {
    private val json = Json { ignoreUnknownKeys = true }

    @Test
    fun uiFrameParsesTouchControlPointsSeparatelyFromBoardPoints() {
        val frame = json.decodeFromString<BoardFrameJson>(
            """
            {
              "board_pts": [[0.10, 0.01], [0.11, 0.02], [0.12, 0.03]],
              "touches": [
                {
                  "id": 1,
                  "px": 960,
                  "py": 540,
                  "mx": 0.15,
                  "my": 0.02,
                  "control_pts": [[0.149, 0.019], [0.150, 0.021]]
                }
              ]
            }
            """.trimIndent(),
        ).toUiFrame()

        assertEquals(3, frame.boardPts.size)
        assertEquals(listOf(0.149f to 0.019f, 0.150f to 0.021f), frame.touches.single().controlPts)
    }
}
