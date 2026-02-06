package dev.uzair.pulselink

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.core.content.ContextCompat
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import dev.uzair.pulselink.ui.screens.ConnectionInfo
import dev.uzair.pulselink.ui.screens.HomeScreen
import dev.uzair.pulselink.ui.screens.QRScannerScreen
import dev.uzair.pulselink.ui.theme.PulseLinkTheme

class MainActivity : ComponentActivity() {
    
    private val requiredPermissions = mutableListOf(
        Manifest.permission.RECORD_AUDIO,
        Manifest.permission.CAMERA
    ).apply {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            add(Manifest.permission.POST_NOTIFICATIONS)
        }
    }
    
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        // Handle permission results if needed
    }
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        
        // Request permissions
        val permissionsToRequest = requiredPermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (permissionsToRequest.isNotEmpty()) {
            permissionLauncher.launch(permissionsToRequest.toTypedArray())
        }
        
        setContent {
            PulseLinkTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = Color(0xFF0f0f14)
                ) {
                    PulseLinkApp()
                }
            }
        }
    }
}

@Composable
fun PulseLinkApp() {
    val navController = rememberNavController()
    var connectionInfo by remember { mutableStateOf<ConnectionInfo?>(null) }
    
    NavHost(
        navController = navController,
        startDestination = "home"
    ) {
        composable("home") {
            HomeScreen(
                onNavigateToScanner = {
                    navController.navigate("scanner")
                },
                connectionInfo = connectionInfo
            )
        }
        
        composable("scanner") {
            QRScannerScreen(
                onConnectionScanned = { info ->
                    connectionInfo = info
                    navController.popBackStack()
                },
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }
    }
}