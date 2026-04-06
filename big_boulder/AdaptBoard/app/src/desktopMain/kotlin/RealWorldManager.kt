import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.InputStream

/**
 * Manages the lifecycle of the physical LD19 LIDAR driver process.
 *
 * States:
 *   DISCONNECTED  — driver not running
 *   CONNECTING    — driver process started, waiting to confirm it is alive
 *   CONNECTED     — driver running and publishing /scan
 *   ERROR         — driver exited unexpectedly or failed to start
 */
class RealWorldManager {

    var status by mutableStateOf(RwStatus.DISCONNECTED)
        private set
    var errorMessage by mutableStateOf<String?>(null)
        private set
    var isVizRunning by mutableStateOf(false)
        private set

    private var lidarProcess: Process? = null
    private var vizProcess: Process? = null

    // ── Connect ───────────────────────────────────────────────────────────────

    suspend fun connect(scope: CoroutineScope) {
        if (status == RwStatus.CONNECTING || status == RwStatus.CONNECTED) return

        status = RwStatus.CONNECTING
        errorMessage = null

        withContext(Dispatchers.IO) {
            try {
                lidarProcess = RosBridge.startRealWorldLidar()

                // Give the driver a moment to start (or crash)
                delay(2500)

                if (lidarProcess?.isAlive == true) {
                    status = RwStatus.CONNECTED
                    // Monitor in background so connect() can return to the UI
                    scope.launch(Dispatchers.IO) { monitorProcess() }
                } else {
                    val errText = lidarProcess?.errorStream?.bufferedReader()
                        ?.readText()?.take(200)
                    status = RwStatus.ERROR
                    errorMessage = "LIDAR driver exited early: ${errText ?: "Unknown error"}"
                    lidarProcess = null
                }
            } catch (e: Exception) {
                status = RwStatus.ERROR
                errorMessage = e.message
                lidarProcess = null
            }
        }
    }

    // ── Disconnect ────────────────────────────────────────────────────────────

    fun disconnect() {
        stopViz()
        lidarProcess?.let { proc ->
            try {
                proc.toHandle().descendants().forEach { it.destroyForcibly() }
            } catch (_: Exception) { /* best effort */ }
            proc.destroyForcibly()
        }
        lidarProcess = null
        status = RwStatus.DISCONNECTED
        errorMessage = null
    }

    // ── Visualization (RViz2) ─────────────────────────────────────────────────

    fun launchViz() {
        if (isVizRunning) return
        vizProcess = RosBridge.launchVisualization()
        isVizRunning = true
    }

    fun stopViz() {
        vizProcess?.let { proc ->
            try { proc.toHandle().descendants().forEach { it.destroyForcibly() } } catch (_: Exception) {}
            proc.destroyForcibly()
        }
        vizProcess = null
        isVizRunning = false
    }

    // ── Stream access (for log panel) ─────────────────────────────────────────

    fun getInputStream(): InputStream? = lidarProcess?.inputStream

    // ── Internal ──────────────────────────────────────────────────────────────

    private fun monitorProcess() {
        lidarProcess?.waitFor()
        if (status == RwStatus.CONNECTED) {
            status = RwStatus.ERROR
            errorMessage = "LIDAR driver terminated unexpectedly"
            lidarProcess = null
        }
    }
}
