import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Manages the lifecycle of the ROS 2 Gazebo simulation process.
 * Tracks state (LAUNCHING, RUNNING, STOPPED, ERROR) and automatically
 * monitors the process to detect unexpected termination.
 */
class SimulationManager {
    var status by mutableStateOf(SimStatus.STOPPED)
        private set
    var errorMessage by mutableStateOf<String?>(null)
        private set

    private var simProcess: Process? = null

    suspend fun launch() {
        // Prevent double-launch
        if (status == SimStatus.LAUNCHING || status == SimStatus.RUNNING) return
        
        status = SimStatus.LAUNCHING
        errorMessage = null
        
        withContext(Dispatchers.IO) {
            try {
                simProcess = RosBridge.launchSimulation()
                // Wait briefly to give Gazebo time to crash if it's going to immediately
                delay(3000)
                if (simProcess?.isAlive == true) {
                    status = SimStatus.RUNNING
                    // Monitor in a SEPARATE coroutine so launch() can return to the UI
                    CoroutineScope(Dispatchers.IO).launch { monitorProcess() }
                } else {
                    status = SimStatus.ERROR
                    // stderr is a separate stream now; read stdout which may have error info
                    val output = simProcess?.inputStream?.bufferedReader()?.readText()?.take(300)
                    errorMessage = "Simulation exited early: ${output ?: "Unknown error"}"
                    simProcess = null
                }
            } catch (e: Exception) {
                status = SimStatus.ERROR
                errorMessage = e.message
                simProcess = null
            }
        }
    }

    fun stop() {
        simProcess?.let { proc ->
            // Kill the entire process tree: Gazebo, gzserver, gzclient, ROS nodes
            // are spawned as grandchildren of the bash shell — destroyForcibly()
            // alone only kills the bash shell, leaving everything else alive.
            try {
                proc.toHandle().descendants().forEach { it.destroyForcibly() }
            } catch (_: Exception) { /* best effort */ }
            proc.destroyForcibly()
        }
        simProcess = null
        status = SimStatus.STOPPED
        errorMessage = null
    }

    /** Expose process stdout for the live log panel. */
    fun getProcessInputStream(): java.io.InputStream? = simProcess?.inputStream

    /**
     * Blocks on the process exit value in the background.
     * If it dies while we still consider it RUNNING, flip to ERROR.
     */
    private fun monitorProcess() {
        simProcess?.waitFor()
        if (status == SimStatus.RUNNING) {
            status = SimStatus.ERROR
            errorMessage = "Simulation terminated unexpectedly"
            simProcess = null
        }
    }
}
