import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.dp

// ─── Board Configuration ─────────────────────────────────────────────────────

/**
 * Describes the inner solid grey rectangle ("the board").
 *
 * @param widthFraction   Width as a fraction of the canvas width  (0..1)
 * @param heightFraction  Height as a fraction of the canvas height (0..1)
 * @param cornerRadius    Corner radius in dp (0 = sharp corners)
 * @param fillColor       Fill colour
 * @param strokeColor     Border colour
 * @param strokeWidth     Border thickness in px
 */
data class BoardConfig(
    val widthFraction:  Float = 0.38f,
    val heightFraction: Float = 0.40f,
    val cornerRadius:   Float = 0f,
    val fillColor:      Color = AppColors.solidRect,
    val strokeColor:    Color = AppColors.dashedLine,
    val strokeWidth:    Float = 3f
)

// ─── Draw Extension ──────────────────────────────────────────────────────────

/**
 * Draws the board (inner solid rectangle) centred in the current DrawScope.
 */
fun DrawScope.drawBoard(config: BoardConfig = BoardConfig()) {
    val cx = size.width  / 2f
    val cy = size.height / 2f
    val w  = size.width  * config.widthFraction
    val h  = size.height * config.heightFraction
    val topLeft = Offset(cx - w / 2, cy - h / 2)

    // Fill
    drawRect(config.fillColor, topLeft, Size(w, h))

    // Stroke
    drawRect(
        config.strokeColor, topLeft, Size(w, h),
        style = Stroke(config.strokeWidth)
    )
}
