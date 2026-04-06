import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

// ─── About Page ──────────────────────────────────────────────────────────────

@Composable
fun AboutPage(onBack: () -> Unit) {
    Column(Modifier.fillMaxSize().background(Color.White)) {
        TopAppBar(
            backgroundColor = AppColors.primary,
            title = { Text("About", color = Color.White) },
            navigationIcon = {
                IconButton(onClick = onBack) {
                    Icon(Icons.Default.ArrowBack, "Back", tint = Color.White)
                }
            }
        )
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Box(
                    Modifier.size(80.dp).background(AppColors.primary, CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Text("A", color = Color.White, fontSize = 40.sp, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.height(20.dp))
                Text("Adapt Board", fontSize = 28.sp, fontWeight = FontWeight.Bold, color = AppColors.text)
                Text(
                    "v1.0.0", fontSize = 14.sp, color = Color.Gray,
                    modifier = Modifier.padding(top = 4.dp, bottom = 16.dp)
                )
                Divider(Modifier.width(200.dp).padding(bottom = 16.dp))
                Text("ROS 2 Simulation Control Hub", fontSize = 16.sp, color = AppColors.text)
                Text(
                    "for the adapt_display package", fontSize = 14.sp, color = Color.Gray,
                    modifier = Modifier.padding(top = 4.dp, bottom = 24.dp)
                )
                Text("Built with Kotlin + Compose Desktop", fontSize = 13.sp, color = Color.LightGray)
            }
        }
    }
}
