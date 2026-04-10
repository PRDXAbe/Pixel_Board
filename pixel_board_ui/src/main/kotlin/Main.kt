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
    // projectRoot is passed by Gradle via -DprojectRoot=...
    // Fall back to parent of CWD (useful when running: cd pixel_board_ui && ./gradlew run)
    val projectRoot = System.getProperty("projectRoot")
        ?: File(System.getProperty("user.dir")).parent
        ?: System.getProperty("user.dir")

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
