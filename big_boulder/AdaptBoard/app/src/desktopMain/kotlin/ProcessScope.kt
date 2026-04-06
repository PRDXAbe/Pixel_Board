import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Utility to run shell subprocesses (like RosBridge calls) on a background thread
 * so they don't block the UI, and return their result.
 *
 * Reads stdout and stderr concurrently to avoid blocking on full pipe buffers.
 */
object ProcessScope {
    suspend fun runAndWait(block: () -> Process): Result<String> =
        withContext(Dispatchers.IO) {
            try {
                val process = block()
                val stdout = StringBuilder()
                val stderr = StringBuilder()
                val t1 = Thread { stdout.append(process.inputStream.bufferedReader().readText()) }
                val t2 = Thread { stderr.append(process.errorStream.bufferedReader().readText()) }
                t1.start(); t2.start()
                t1.join(); t2.join()
                val exitCode = process.waitFor()
                if (exitCode == 0) {
                    Result.success(stdout.toString())
                } else {
                    Result.failure(RuntimeException("Exit $exitCode: ${stderr.toString().take(500)}"))
                }
            } catch (e: Exception) {
                Result.failure(e)
            }
        }
}
