import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

// ─── Simulation Configuration ────────────────────────────────────────────────
//
// All tuneable parameters for ball simulation and lidar scanning,
// grouped under Ball and Lidar. Hoisted into AdaptBoardApp state
// so both the MainBoardPage and SettingsPage can read/write them.
//
// Value‑type legend (from the spec):
//   t1 = positive integer, 0 … +∞
//   (t2, t3, t4 reserved for future use)

// ── Ball ─────────────────────────────────────────────────────────────────────

data class BallConfig(
    val radius:    Int = 5,    // t1 – radius of simulated balls
    val mass:      Int = 1,    // t1 – mass of each simulated ball
    val throwDist: Int = 10    // t1 – distance from which balls are thrown
)

// ── Board ────────────────────────────────────────────────────────────────────

data class BoardSettings(
    val boardWidth:   Int = 6,    // t1 – actual board width in meters
    val boardHeight:  Int = 4,    // t1 – actual board height in meters
    val marginWidth:  Int = 10,   // t1 – dashed imaginary margin width in meters
    val marginHeight: Int = 8     // t1 – dashed imaginary margin height in meters
)

// ── Lidar ────────────────────────────────────────────────────────────────────

enum class LidarPlacementAxis { VERTICAL, HORIZONTAL }

// ─── View Mode ────────────────────────────────────────────────────────────────

enum class ViewMode { TOP_DOWN, FRONT_ELEVATION }

data class LidarConfig(
    val scanFrequency: Int = 100,  // t1 – scanning frequency (Hz)
    val maxRange:      Int = 6,    // t1 – detection range (meters)
    val scanCounts:    Int = 1,    // t1 – points to confirm single vs. multiple balls (1 = single hit registers)
    val scanCloseness: Int = 1,    // t1 – distance between scans for uniqueness
    val scanHideAngle: Int = 15,   // t1 – angle hidden to avoid floor/wall detections
    val placementAxis: LidarPlacementAxis = LidarPlacementAxis.VERTICAL // Axis of restriction
)
//
// ── Aggregate ────────────────────────────────────────────────────────────────

data class SimulationConfig(
    val ball:  BallConfig    = BallConfig(),
    val board: BoardSettings = BoardSettings(),
    val lidar: LidarConfig   = LidarConfig()
)

// ── Save Result ──────────────────────────────────────────────────────────────

sealed class SaveResult {
    object Success : SaveResult()
    object SuccessWithRebuild : SaveResult()
    data class Error(val message: String) : SaveResult()
}

// ── Simulation Lifecycle Status ──────────────────────────────────────────────

enum class SimStatus { STOPPED, LAUNCHING, RUNNING, ERROR }

// ── Observable wrapper for easy hoisting in Compose ──────────────────────────

class SimulationConfigState {
    var config by mutableStateOf(SimulationConfig())
        private set

    /** Snapshot of last saved config — used to detect what changed. */
    var lastSavedConfig by mutableStateOf(SimulationConfig())
        private set

    /** Mark the current config as "saved". */
    fun markSaved() { lastSavedConfig = config }

    /**
     * Returns true if any URDF-baked param changed since last save.
     * These require a `colcon build` to take effect.
     */
    fun needsRebuild(): Boolean {
        return config.ball.radius != lastSavedConfig.ball.radius ||
               config.ball.mass   != lastSavedConfig.ball.mass   ||
               config.lidar.scanFrequency != lastSavedConfig.lidar.scanFrequency
    }

    // Ball mutators
    fun setBallRadius(v: Int)    { config = config.copy(ball = config.ball.copy(radius    = v.coerceAtLeast(0))) }
    fun setBallMass(v: Int)      { config = config.copy(ball = config.ball.copy(mass      = v.coerceAtLeast(0))) }
    fun setBallThrowDist(v: Int) { config = config.copy(ball = config.ball.copy(throwDist = v.coerceAtLeast(0))) }

    // Board mutators — enforce board ≤ margin
    fun setBoardWidth(v: Int)    { config = config.copy(board = config.board.copy(boardWidth   = v.coerceIn(1, config.board.marginWidth))) }
    fun setBoardHeight(v: Int)   { config = config.copy(board = config.board.copy(boardHeight  = v.coerceIn(1, config.board.marginHeight))) }
    fun setMarginWidth(v: Int)   { val clamped = v.coerceAtLeast(1); config = config.copy(board = config.board.copy(marginWidth = clamped, boardWidth = config.board.boardWidth.coerceAtMost(clamped))) }
    fun setMarginHeight(v: Int)  { val clamped = v.coerceAtLeast(1); config = config.copy(board = config.board.copy(marginHeight = clamped, boardHeight = config.board.boardHeight.coerceAtMost(clamped))) }

    // Lidar mutators
    fun setScanFrequency(v: Int) { config = config.copy(lidar = config.lidar.copy(scanFrequency = v.coerceAtLeast(0))) }
    fun setMaxRange(v: Int)      { config = config.copy(lidar = config.lidar.copy(maxRange      = v.coerceAtLeast(0))) }
    fun setScanCounts(v: Int)    { config = config.copy(lidar = config.lidar.copy(scanCounts    = v.coerceAtLeast(0))) }
    fun setScanCloseness(v: Int) { config = config.copy(lidar = config.lidar.copy(scanCloseness = v.coerceAtLeast(0))) }
    fun setScanHideAngle(v: Int) { config = config.copy(lidar = config.lidar.copy(scanHideAngle = v.coerceAtLeast(0))) }
    fun setLidarPlacementAxis(axis: LidarPlacementAxis) { config = config.copy(lidar = config.lidar.copy(placementAxis = axis)) }
}
