package com.pixelboard.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.pixelboard.AppViewModel

@Composable
fun MainScreen(viewModel: AppViewModel) {
    val state by viewModel.state.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BackgroundDeep),
    ) {
        // ── Top bar ───────────────────────────────────────────────────────────
        TopBar(state = state)

        // ── Error banner ──────────────────────────────────────────────────────
        AnimatedVisibility(
            visible = state.errorMessage != null,
            enter   = fadeIn(),
            exit    = fadeOut(),
        ) {
            state.errorMessage?.let { msg ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(AccentRed.copy(alpha = 0.15f))
                        .padding(horizontal = 16.dp, vertical = 6.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Text(msg, color = AccentRed, style = MaterialTheme.typography.bodySmall)
                    IconButton(onClick = { viewModel.dismissError() }, modifier = Modifier.size(18.dp)) {
                        Icon(Icons.Filled.Close, contentDescription = "Dismiss", tint = AccentRed)
                    }
                }
            }
        }

        // ── Main content ──────────────────────────────────────────────────────
        Row(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .padding(8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            // Left: controls
            ControlPanel(
                state     = state,
                viewModel = viewModel,
                modifier  = Modifier
                    .width(240.dp)
                    .fillMaxHeight()
                    .clip(RoundedCornerShape(12.dp)),
            )

            // Centre: LIDAR canvas
            LidarCanvas(
                frame    = state.frame,
                screenPreview = state.screenPreview.takeIf { state.interactiveModeEnabled },
                modifier = Modifier
                    .weight(1f)
                    .fillMaxHeight(),
            )

            // Right: touch output
            TouchPanel(
                state    = state,
                modifier = Modifier
                    .width(240.dp)
                    .fillMaxHeight()
                    .clip(RoundedCornerShape(12.dp)),
            )
        }

        // ── Status bar ────────────────────────────────────────────────────────
        StatusBar(state = state)
    }
}
