import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke

// ─── Support Configuration ───────────────────────────────────────────────────

/**
 * Describes the outer dashed rectangle ("the support frame").
 *
 * @param widthFraction   Width as a fraction of canvas width  (0..1)
 * @param heightFraction  Height as a fraction of canvas height (0..1)
 * @param dashOn          Length of visible dash segment in px
 * @param dashOff         Length of gap between dashes in px
 * @param strokeColor     Border colour
 * @param strokeWidth     Border thickness in px
 */
data class SupportConfig(
    val widthFraction:  Float = 0.56f,
    val heightFraction: Float = 0.60f,
    val dashOn:         Float = 10f,
    val dashOff:        Float = 10f,
    val strokeColor:    Color = AppColors.dashedLine,
    val strokeWidth:    Float = 2f
)

// ─── Draw Extension ──────────────────────────────────────────────────────────

/**
 * Draws the support frame (outer dashed rectangle) centred in the current DrawScope.
 */
fun DrawScope.drawSupport(config: SupportConfig = SupportConfig()) {
    val cx = size.width  / 2f
    val cy = size.height / 2f
    val w  = size.width  * config.widthFraction
    val h  = size.height * config.heightFraction
    val topLeft = Offset(cx - w / 2, cy - h / 2)

    val dash = PathEffect.dashPathEffect(
        floatArrayOf(config.dashOn, config.dashOff), 0f
    )

    drawRect(
        config.strokeColor, topLeft, Size(w, h),
        style = Stroke(config.strokeWidth, pathEffect = dash)
    )
}
