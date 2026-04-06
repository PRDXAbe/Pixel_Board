import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke

/**
 * Draws detected ball centroids on the canvas.
 *
 * Converts world coordinates (meters, relative to lidar at origin)
 * to canvas pixel positions using the margin dimensions and support
 * fractions as the scale reference.
 */
fun DrawScope.drawDetectedBalls(
    balls: List<Pair<Float, Float>>,   // (worldX, worldY) in meters
    lidarState: LidarState,            // current lidar canvas position
    marginWidthM: Float,               // margin width in meters
    marginHeightM: Float,              // margin height in meters
    supportWFrac: Float,               // support fraction of canvas width
    supportHFrac: Float                // support fraction of canvas height
) {
    if (balls.isEmpty()) return

    // Pixels per meter — derived from the support rect (which represents the margin)
    val supportWidthPx  = size.width  * supportWFrac
    val supportHeightPx = size.height * supportHFrac
    val pxPerMeterX = if (marginWidthM  > 0) supportWidthPx  / marginWidthM  else 1f
    val pxPerMeterY = if (marginHeightM > 0) supportHeightPx / marginHeightM else 1f

    for ((wx, wy) in balls) {
        // World coords are relative to lidar at origin
        val canvasX = lidarState.x + wx * pxPerMeterX
        val canvasY = lidarState.y - wy * pxPerMeterY  // Y inverted (canvas Y grows down)

        // Filled red dot
        drawCircle(
            color = Color.Red.copy(alpha = 0.85f),
            radius = 6f,
            center = Offset(canvasX, canvasY)
        )
        // Outer glow ring
        drawCircle(
            color = Color.Red.copy(alpha = 0.3f),
            radius = 12f,
            center = Offset(canvasX, canvasY),
            style = Stroke(2f)
        )
    }
}
