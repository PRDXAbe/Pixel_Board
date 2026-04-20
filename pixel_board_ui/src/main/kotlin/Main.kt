import androidx.compose.ui.unit.DpSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.WindowState
import androidx.compose.ui.window.application
import com.pixelboard.AppViewModel
import com.pixelboard.ui.MainScreen
import com.pixelboard.ui.PixelBoardTheme
import java.io.File

fun main() {
    val projectRoot = resolveProjectRoot()

    val viewModel = AppViewModel(projectRoot)

    application {
        Window(
            onCloseRequest = {
                viewModel.dispose()
                exitApplication()
            },
            title = "PixelBoard",
            state = WindowState(size = DpSize(1400.dp, 860.dp)),
            resizable = true,
        ) {
            PixelBoardTheme {
                MainScreen(viewModel = viewModel)
            }
        }
    }
}

private fun resolveProjectRoot(): String {
    val candidates = buildList {
        System.getProperty("projectRoot")?.let(::add)
        System.getProperty("user.dir")?.let(::add)
    }

    candidates.forEach { rawPath ->
        findProjectRoot(File(rawPath))?.let { return it.absolutePath }
    }

    return candidates.firstOrNull() ?: "."
}

private fun findProjectRoot(start: File): File? {
    val absoluteStart = start.absoluteFile

    searchUpwardForProjectRoot(absoluteStart)?.let { return it }

    // Some IDE/Gradle launch paths pass the parent directory of the repo rather than the
    // repo root itself. Search a shallow child window so we can still find Pixel_Board.
    absoluteStart
        .walkTopDown()
        .maxDepth(2)
        .firstOrNull(::isProjectRoot)
        ?.let { return it.absoluteFile }

    return null
}

private fun searchUpwardForProjectRoot(start: File): File? {
    var current: File? = start
    while (current != null) {
        if (isProjectRoot(current)) {
            return current
        }
        current = current.parentFile
    }
    return null
}

private fun isProjectRoot(dir: File): Boolean =
    File(dir, "board_config.json").isFile && File(dir, "pixel_board_ui").isDirectory
