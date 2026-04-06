// ─── Bridge: ROS 2 Integration Layer ─────────────────────────────────────────
//
// This module acts as the bridge between the Adapt Board UI and the
// ROS 2 environment (adapt_display package).
//
// All ROS 2 interactions happen via shell subprocess calls.
// The workspace must be sourced first:
//   source /home/xanta/big_boulder/install/setup.bash

/**
 * Bridge to the ROS 2 adapt_display system.
 *
 * Each method constructs and executes a shell command using ProcessBuilder.
 * Parameters mirror those documented in AGENT_INTERFACE.md §2.
 */
object RosBridge {

    private const val WORKSPACE = "/home/abhinav/Projects/Magic_Board/big_boulder"
    private const val SOURCE_CMD = "source $WORKSPACE/install/setup.bash"

    // ── Simulation ───────────────────────────────────────────────────────

    /**
     * Launch the Gazebo simulation (long-running).
     * Must be called before any other ROS 2 command.
     */
    fun launchSimulation(): Process {
        return runBash("$SOURCE_CMD && ros2 launch adapt_display launch_simulation.launch.py")
    }

    // ── Spawning ─────────────────────────────────────────────────────────

    /**
     * Spawn a single ball.
     *
     * All bounds are in meters in lidar-world space (lidar = world origin).
     * The UI computes them from the canvas positions of the board/margin
     * rectangles relative to the lidar dot, so balls always fall where
     * the lidar can actually see them.
     */
    fun spawnSingleBall(
        config: SimulationConfig,
        boardMinX: Double, boardMaxX: Double,
        boardMinY: Double, boardMaxY: Double,
        marginMinX: Double, marginMaxX: Double,
        marginMinY: Double, marginMaxY: Double
    ): Process {
        val h = config.ball.throwDist.toDouble()
        return runBash(
            "$SOURCE_CMD && ros2 run adapt_display spawn_single_ball.py --ros-args " +
            "-p board_min_x:=$boardMinX -p board_max_x:=$boardMaxX " +
            "-p board_min_y:=$boardMinY -p board_max_y:=$boardMaxY " +
            "-p margin_min_x:=$marginMinX -p margin_max_x:=$marginMaxX " +
            "-p margin_min_y:=$marginMinY -p margin_max_y:=$marginMaxY " +
            "-p spawn_height:=$h"
        )
    }

    /**
     * Spawn multiple balls with the same world-space bounds.
     */
    fun spawnMultipleBalls(
        numBalls: Int = 10,
        config: SimulationConfig,
        boardMinX: Double, boardMaxX: Double,
        boardMinY: Double, boardMaxY: Double,
        marginMinX: Double, marginMaxX: Double,
        marginMinY: Double, marginMaxY: Double
    ): Process {
        val h = config.ball.throwDist.toDouble()
        return runBash(
            "$SOURCE_CMD && ros2 run adapt_display spawn_multiple_balls.py --ros-args " +
            "-p num_balls:=$numBalls " +
            "-p board_min_x:=$boardMinX -p board_max_x:=$boardMaxX " +
            "-p board_min_y:=$boardMinY -p board_max_y:=$boardMaxY " +
            "-p margin_min_x:=$marginMinX -p margin_max_x:=$marginMaxX " +
            "-p margin_min_y:=$marginMinY -p margin_max_y:=$marginMaxY " +
            "-p spawn_height:=$h"
        )
    }

    // ── Removal ──────────────────────────────────────────────────────────

    /**
     * Remove balls. Pass -1 or leave default to remove ALL balls.
     */
    fun removeBalls(numBalls: Int = -1): Process {
        val args = if (numBalls > 0) " --ros-args -p num_balls:=$numBalls" else ""
        return runBash("$SOURCE_CMD && ros2 run adapt_display remove_balls.py$args")
    }

    // ── Tracker ──────────────────────────────────────────────────────────

    /**
     * Start the scan tracker (long-running).
     * Returns Process whose stderr can be read for ball detections.
     * Derives tracker params from SimulationConfig.
     *
     * Board bounds are in world-space meters with the lidar at the origin.
     * Only LIDAR hits inside this rectangle are clustered and counted.
     *
     *
     * Board filtering is enabled by default — only balls whose LIDAR scan
     * hit falls within the physical drawing board are counted.
     *
     * Bounds are in SENSOR-FRAME coordinates. With the LIDAR spawned at
     * world (0, 0.2) and yaw = -π/2:
     *   sensor_x = -(world_Y - 0.2)   →  board near edge 0.15, far edge 2.65
     *   sensor_y =   world_X           →  board left -1.55, right +1.55
     * (5 cm margin added to catch balls sitting exactly on an edge.)
     */
    fun startTracker(config: SimulationConfig): Process {
        val distanceThreshold   = config.lidar.scanCloseness.toDouble()
        val minPointsPerCluster = config.lidar.scanCounts
        // Physical board: 3.0 m × 2.4 m, spawned at world (0, -1.2, 0.8)
        //   World Y span: 0.0 .. -2.4  →  sensor_x: 0.15 .. 2.65
        //   World X span: -1.5 .. 1.5  →  sensor_y: -1.55 .. 1.55
        val boardMinX = 0.15
        val boardMaxX = 2.65
        val boardMinY = -1.55
        val boardMaxY = 1.55
        return runBash(
            "$SOURCE_CMD && ros2 run adapt_display scan_tracker --ros-args " +
            "-p distance_threshold:=$distanceThreshold " +
            "-p min_points_per_cluster:=$minPointsPerCluster " +
            "-p enable_board_filtering:=true " +
            "-p board_min_x:=$boardMinX -p board_max_x:=$boardMaxX " +
            "-p board_min_y:=$boardMinY -p board_max_y:=$boardMaxY"
        )
    }

    // ── Build ────────────────────────────────────────────────────────────

    /**
     * Rebuild the adapt_display package (only if source changed).
     */
    fun buildPackage(): Process {
        return runBash("cd $WORKSPACE && colcon build --packages-select adapt_display")
    }

    // ── Internal ─────────────────────────────────────────────────────────

    private fun runBash(command: String): Process {
        return ProcessBuilder("bash", "-c", command)
            .start()
    }
}
