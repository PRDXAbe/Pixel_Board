import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

/**
 * Parses the stdout of `scan_tracker` to extract ball centroid positions
 * and the running total ball count.
 *
 * The tracker outputs lines like:
 *   --- Detected 2 Balls --- | Total Count: 5
 *   Ball 1: Centroid X (0.523), Y (1.234) | Points: 4
 *   Ball 2: Centroid X (-0.100), Y (0.800) | Points: 3
 */
class TrackerParser {
    var detections by mutableStateOf<List<Pair<Float, Float>>>(emptyList())
        private set
    var frameCount by mutableStateOf(0)
        private set
    /** Running total of unique ball events (new + reappearances). */
    var totalBallCount by mutableStateOf(0)
        private set

    private var process: Process? = null
    private var parseJob: Job? = null

    private val centroidRegex = Regex("""Ball \d+: Centroid X \((-?[\d.]+)\), Y \((-?[\d.]+)\)""")
    private val totalRegex = Regex("""Total Count: (\d+)""")

    fun start(config: SimulationConfig, scope: CoroutineScope) {
        stop()
        scope.launch(Dispatchers.IO) {
            process = RosBridge.startTracker(config)
            parseJob = launch {
                // ROS2 RCLCPP_INFO writes to stderr, not stdout
                process?.errorStream?.bufferedReader()?.useLines { lines ->
                    var currentBatch = mutableListOf<Pair<Float, Float>>()
                    for (line in lines) {
                        if ("--- Detected" in line) {
                            // Commit previous batch (may be empty if no balls last frame)
                            detections = currentBatch.toList()
                            frameCount++
                            currentBatch = mutableListOf()
                            // Parse total count from this line
                            totalRegex.find(line)?.let { m ->
                                m.groupValues[1].toIntOrNull()?.let { totalBallCount = it }
                            }
                        }
                        centroidRegex.find(line)?.let { match ->
                            val x = match.groupValues[1].toFloatOrNull() ?: return@let
                            val y = match.groupValues[2].toFloatOrNull() ?: return@let
                            currentBatch.add(x to y)
                        }
                    }
                }
            }
        }
    }

    fun stop() {
        parseJob?.cancel()
        parseJob = null
        process?.let { proc ->
            try {
                proc.toHandle().descendants().forEach { it.destroyForcibly() }
            } catch (_: Exception) {}
            proc.destroyForcibly()
        }
        process = null
        detections = emptyList()
        frameCount = 0
        totalBallCount = 0
    }
}
