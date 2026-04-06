import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

// ─── Shared Color Palette ────────────────────────────────────────────────────

object AppColors {
    val primary    = Color(0xFF1E3A5F)
    val text       = Color(0xFF2C3E50)
    val grid       = Color(0xFFE0E0E0)
    val dashedLine = Color(0xFF34495E)
    val solidRect  = Color(0xFFD6DBDF)
    val sidebar    = Color(0xFFF0F1F3)
    val drawerBg   = Color(0xFF1A2940)
    val accent     = Color(0xFF56A8F5)
    val danger     = Color(0xFFFF6B6B)
}

// ─── Navigation ──────────────────────────────────────────────────────────────

enum class Page { MAIN, SETTINGS, ABOUT }

// ─── Drawer ──────────────────────────────────────────────────────────────────

@Composable
fun DrawerContent(
    onSettings: () -> Unit,
    onAbout:    () -> Unit,
    onQuit:     () -> Unit,
    simManager: SimulationManager? = null,
    scope: CoroutineScope? = null
) {
    Column(
        modifier = Modifier
            .fillMaxHeight()
            .width(280.dp)
            .shadow(12.dp)
            .background(AppColors.drawerBg)
            .padding(28.dp)
    ) {
        Text("Adapt Board", color = Color.White, fontSize = 22.sp,
            fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 8.dp))
        Text("ROS 2 Simulation Hub", color = Color.White.copy(alpha = 0.6f),
            fontSize = 13.sp, modifier = Modifier.padding(bottom = 24.dp))
        Divider(color = Color.White.copy(alpha = 0.15f), modifier = Modifier.padding(bottom = 20.dp))

        if (simManager != null && scope != null) {
            val isRunning = simManager.status == SimStatus.RUNNING || simManager.status == SimStatus.LAUNCHING
            DrawerItem(
                icon = { 
                    if (isRunning) Text("⏹", color = AppColors.danger, fontSize = 18.sp)
                    else Text("▶", color = Color.Green, fontSize = 18.sp) 
                },
                label = if (isRunning) "Stop Simulation" else "Launch Simulation",
                onClick = {
                    if (isRunning) simManager.stop()
                    else scope.launch { simManager.launch() }
                }
            )
            Spacer(Modifier.height(16.dp))
        }

        DrawerItem(
            icon = { Icon(Icons.Default.Settings, null, tint = Color.White) },
            label = "Settings", onClick = onSettings
        )
        Spacer(Modifier.height(8.dp))
        DrawerItem(
            icon = { Icon(Icons.Default.Info, null, tint = Color.White) },
            label = "About", onClick = onAbout
        )

        Spacer(Modifier.weight(1f))

        Divider(color = Color.White.copy(alpha = 0.15f), modifier = Modifier.padding(bottom = 16.dp))
        DrawerItem(
            icon = { Text("⏻", color = AppColors.danger, fontSize = 18.sp) },
            label = "Quit",
            labelColor = AppColors.danger,
            onClick = onQuit
        )
    }
}

@Composable
fun DrawerItem(
    icon: @Composable () -> Unit,
    label: String,
    labelColor: Color = Color.White,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .clickable(
                indication = null,
                interactionSource = remember { MutableInteractionSource() },
                onClick = onClick
            )
            .padding(horizontal = 12.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        icon()
        Text(label, color = labelColor, fontSize = 16.sp, fontWeight = FontWeight.Medium)
    }
}

// ─── Utility: background extension that doesn't need its own import ─────────
// (Compose foundation background is imported in each file individually)
