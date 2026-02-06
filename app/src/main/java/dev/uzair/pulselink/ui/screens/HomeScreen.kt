package dev.uzair.pulselink.ui.screens

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.os.IBinder
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import dev.uzair.pulselink.service.AudioStreamService

// Colors matching Linux app theme
val BackgroundColor = Color(0xFF0f0f14)
val CardColor = Color(0xFF1a1a24)
val CardBorderColor = Color(0xFF2a2a3a)
val PrimaryBlue = Color(0xFF3b82f6)
val PrimaryBlueDark = Color(0xFF2563eb)
val SuccessGreen = Color(0xFF22c55e)
val DangerRed = Color(0xFFEF4444)
val WarningOrange = Color(0xFFF59E0B)
val TextPrimary = Color(0xFFe0e0f0)
val TextSecondary = Color(0xFF888899)

data class StreamingState(
    val isConnected: Boolean = false,
    val isStreaming: Boolean = false,
    val serverIp: String = "",
    val serverPort: Int = 5555,
    val audioLevel: Float = 0f,
    val packetsSent: Int = 0,
    val error: String? = null
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    onNavigateToScanner: () -> Unit,
    connectionInfo: ConnectionInfo?
) {
    val context = LocalContext.current
    var streamingState by remember { mutableStateOf(StreamingState()) }
    var service by remember { mutableStateOf<AudioStreamService?>(null) }
    
    // Update state when connection info received
    LaunchedEffect(connectionInfo) {
        connectionInfo?.let {
            streamingState = streamingState.copy(
                serverIp = it.ip,
                serverPort = it.port,
                isConnected = true
            )
        }
    }
    
    // Service connection
    val serviceConnection = remember {
        object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
                val localBinder = binder as AudioStreamService.LocalBinder
                service = localBinder.getService().also { svc ->
                    svc.onStreamingStateChanged = { streaming ->
                        streamingState = streamingState.copy(isStreaming = streaming)
                    }
                    svc.onAudioLevel = { level ->
                        streamingState = streamingState.copy(audioLevel = level)
                    }
                    svc.onPacketsSent = { packets ->
                        streamingState = streamingState.copy(packetsSent = packets)
                    }
                    svc.onError = { error ->
                        streamingState = streamingState.copy(error = error)
                    }
                }
            }
            
            override fun onServiceDisconnected(name: ComponentName?) {
                service = null
            }
        }
    }
    
    DisposableEffect(Unit) {
        val intent = Intent(context, AudioStreamService::class.java)
        context.bindService(intent, serviceConnection, Context.BIND_AUTO_CREATE)
        
        onDispose {
            context.unbindService(serviceConnection)
        }
    }
    
    // Start streaming function
    fun startStreaming() {
        if (streamingState.serverIp.isEmpty()) {
            streamingState = streamingState.copy(error = "Scan QR code first")
            return
        }
        
        val intent = Intent(context, AudioStreamService::class.java).apply {
            action = AudioStreamService.ACTION_START
            putExtra(AudioStreamService.EXTRA_SERVER_IP, streamingState.serverIp)
            putExtra(AudioStreamService.EXTRA_SERVER_PORT, streamingState.serverPort)
        }
        context.startForegroundService(intent)
    }
    
    // Stop streaming function
    fun stopStreaming() {
        val intent = Intent(context, AudioStreamService::class.java).apply {
            action = AudioStreamService.ACTION_STOP
        }
        context.startService(intent)
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Default.Podcasts,
                            contentDescription = null,
                            tint = PrimaryBlue
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("PulseLink", fontWeight = FontWeight.Bold)
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = BackgroundColor,
                    titleContentColor = TextPrimary
                )
            )
        },
        containerColor = BackgroundColor
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Spacer(modifier = Modifier.height(8.dp))
            
            // Status Card
            StatusCard(streamingState)
            
            // Connection Card
            ConnectionCard(
                streamingState = streamingState,
                onScanClick = onNavigateToScanner
            )
            
            // Audio Visualizer Card
            if (streamingState.isStreaming) {
                AudioVisualizerCard(level = streamingState.audioLevel)
            }
            
            // Control Button
            StreamingButton(
                isStreaming = streamingState.isStreaming,
                isConnected = streamingState.isConnected,
                onStart = { startStreaming() },
                onStop = { stopStreaming() }
            )
            
            // Error display
            streamingState.error?.let { error ->
                ErrorCard(error = error, onDismiss = {
                    streamingState = streamingState.copy(error = null)
                })
            }
            
            // Stats Card
            if (streamingState.isStreaming) {
                StatsCard(packetsSent = streamingState.packetsSent)
            }
            
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@Composable
fun StatusCard(state: StreamingState) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = CardColor),
        shape = RoundedCornerShape(16.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Status indicator
            StatusDot(
                isConnected = state.isConnected,
                isStreaming = state.isStreaming
            )
            
            Spacer(modifier = Modifier.width(12.dp))
            
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = when {
                        state.isStreaming -> "Streaming"
                        state.isConnected -> "Connected"
                        else -> "Not Connected"
                    },
                    color = TextPrimary,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = when {
                        state.isStreaming -> "Sending audio to ${state.serverIp}"
                        state.isConnected -> "Ready to stream"
                        else -> "Scan QR code to connect"
                    },
                    color = TextSecondary,
                    fontSize = 13.sp
                )
            }
        }
    }
}

@Composable
fun StatusDot(isConnected: Boolean, isStreaming: Boolean) {
    val color = when {
        isStreaming -> SuccessGreen
        isConnected -> WarningOrange
        else -> DangerRed
    }
    
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val scale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = if (isStreaming) 1.3f else 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(1000),
            repeatMode = RepeatMode.Reverse
        ),
        label = "scale"
    )
    
    Box(
        modifier = Modifier
            .size(12.dp)
            .scale(scale)
            .clip(CircleShape)
            .background(color)
    )
}

@Composable
fun ConnectionCard(
    streamingState: StreamingState,
    onScanClick: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = CardColor),
        shape = RoundedCornerShape(16.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp)
        ) {
            Text(
                text = "CONNECTION",
                color = TextSecondary,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 1.sp
            )
            
            Spacer(modifier = Modifier.height(12.dp))
            
            if (streamingState.isConnected) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Default.Computer,
                        contentDescription = null,
                        tint = PrimaryBlue
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Linux Server",
                            color = TextPrimary,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = "${streamingState.serverIp}:${streamingState.serverPort}",
                            color = TextSecondary,
                            fontSize = 13.sp
                        )
                    }
                    IconButton(onClick = onScanClick) {
                        Icon(
                            Icons.Default.Refresh,
                            contentDescription = "Rescan",
                            tint = TextSecondary
                        )
                    }
                }
            } else {
                Button(
                    onClick = onScanClick,
                    modifier = Modifier.fillMaxWidth(),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = PrimaryBlue
                    ),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Icon(Icons.Default.QrCodeScanner, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text("Scan QR Code")
                }
            }
        }
    }
}

@Composable
fun AudioVisualizerCard(level: Float) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = CardColor),
        shape = RoundedCornerShape(16.dp)
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp)
        ) {
            Text(
                text = "AUDIO LEVEL",
                color = TextSecondary,
                fontSize = 12.sp,
                fontWeight = FontWeight.SemiBold,
                letterSpacing = 1.sp
            )
            
            Spacer(modifier = Modifier.height(12.dp))
            
            // Simple bar visualizer
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(40.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.Bottom
            ) {
                repeat(12) { index ->
                    val barLevel = (level * 12).toInt()
                    val isActive = index < barLevel
                    
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxHeight(if (isActive) 0.3f + (level * 0.7f) else 0.15f)
                            .clip(RoundedCornerShape(4.dp))
                            .background(
                                if (isActive) {
                                    Brush.verticalGradient(
                                        colors = listOf(
                                            PrimaryBlue.copy(alpha = 0.9f),
                                            PrimaryBlueDark
                                        )
                                    )
                                } else {
                                    Brush.verticalGradient(
                                        colors = listOf(
                                            CardBorderColor,
                                            CardBorderColor
                                        )
                                    )
                                }
                            )
                    )
                }
            }
        }
    }
}

@Composable
fun StreamingButton(
    isStreaming: Boolean,
    isConnected: Boolean,
    onStart: () -> Unit,
    onStop: () -> Unit
) {
    Button(
        onClick = { if (isStreaming) onStop() else onStart() },
        modifier = Modifier
            .fillMaxWidth()
            .height(56.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (isStreaming) DangerRed else PrimaryBlue
        ),
        shape = RoundedCornerShape(12.dp),
        enabled = isConnected || isStreaming
    ) {
        Icon(
            if (isStreaming) Icons.Default.Stop else Icons.Default.Mic,
            contentDescription = null
        )
        Spacer(modifier = Modifier.width(8.dp))
        Text(
            text = if (isStreaming) "Stop Streaming" else "Start Streaming",
            fontSize = 16.sp,
            fontWeight = FontWeight.SemiBold
        )
    }
}

@Composable
fun ErrorCard(error: String, onDismiss: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = DangerRed.copy(alpha = 0.1f)
        ),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                Icons.Default.Error,
                contentDescription = null,
                tint = DangerRed
            )
            Spacer(modifier = Modifier.width(12.dp))
            Text(
                text = error,
                color = DangerRed,
                modifier = Modifier.weight(1f)
            )
            IconButton(onClick = onDismiss) {
                Icon(
                    Icons.Default.Close,
                    contentDescription = "Dismiss",
                    tint = DangerRed
                )
            }
        }
    }
}

@Composable
fun StatsCard(packetsSent: Int) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = CardColor),
        shape = RoundedCornerShape(16.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            StatItem(label = "Packets Sent", value = packetsSent.toString())
            StatItem(label = "Protocol", value = "UDP")
            StatItem(label = "Sample Rate", value = "48kHz")
        }
    }
}

@Composable
fun StatItem(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            color = PrimaryBlue,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = label,
            color = TextSecondary,
            fontSize = 11.sp
        )
    }
}
