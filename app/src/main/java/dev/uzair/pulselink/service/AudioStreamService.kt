package dev.uzair.pulselink.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import dev.uzair.pulselink.MainActivity
import dev.uzair.pulselink.R
import dev.uzair.pulselink.audio.AudioCapture
import dev.uzair.pulselink.network.NetworkClient
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.collect

/**
 * Foreground service for continuous audio streaming
 * Keeps running even when app is minimized
 */
class AudioStreamService : Service() {
    
    companion object {
        private const val TAG = "AudioStreamService"
        private const val NOTIFICATION_ID = 1
        private const val CHANNEL_ID = "pulselink_streaming"
        
        // Intent actions
        const val ACTION_START = "dev.uzair.pulselink.START"
        const val ACTION_STOP = "dev.uzair.pulselink.STOP"
        
        // Intent extras
        const val EXTRA_SERVER_IP = "server_ip"
        const val EXTRA_SERVER_PORT = "server_port"
    }
    
    private val binder = LocalBinder()
    private val serviceScope = CoroutineScope(Dispatchers.Default + SupervisorJob())
    
    private var audioCapture: AudioCapture? = null
    private var networkClient: NetworkClient? = null
    private var streamingJob: Job? = null
    
    // State
    private var isStreaming = false
    private var serverIp: String = ""
    private var serverPort: Int = 5555
    
    // Callbacks for UI updates
    var onStreamingStateChanged: ((Boolean) -> Unit)? = null
    var onAudioLevel: ((Float) -> Unit)? = null
    var onError: ((String) -> Unit)? = null
    var onPacketsSent: ((Int) -> Unit)? = null
    
    inner class LocalBinder : Binder() {
        fun getService(): AudioStreamService = this@AudioStreamService
    }
    
    override fun onBind(intent: Intent?): IBinder = binder
    
    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        
        audioCapture = AudioCapture(this)
        networkClient = NetworkClient()
        
        // Set up callbacks
        audioCapture?.onAudioLevel = { level ->
            onAudioLevel?.invoke(level)
        }
        
        networkClient?.onError = { error ->
            onError?.invoke(error)
        }
        
        networkClient?.onConnectionStateChanged = { connected ->
            if (!connected && isStreaming) {
                stopStreaming()
            }
        }
    }
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> {
                serverIp = intent.getStringExtra(EXTRA_SERVER_IP) ?: ""
                serverPort = intent.getIntExtra(EXTRA_SERVER_PORT, 5555)
                
                if (serverIp.isNotEmpty()) {
                    startForeground(NOTIFICATION_ID, createNotification())
                    startStreaming()
                }
            }
            ACTION_STOP -> {
                stopStreaming()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return START_NOT_STICKY
    }
    
    override fun onDestroy() {
        stopStreaming()
        serviceScope.cancel()
        super.onDestroy()
    }
    
    /**
     * Start audio streaming
     */
    private fun startStreaming() {
        if (isStreaming) return
        
        streamingJob = serviceScope.launch {
            try {
                // Connect to server
                val connected = networkClient?.connect(serverIp, serverPort) ?: false
                if (!connected) {
                    withContext(Dispatchers.Main) {
                        onError?.invoke("Failed to connect to server")
                    }
                    return@launch
                }
                
                isStreaming = true
                withContext(Dispatchers.Main) {
                    onStreamingStateChanged?.invoke(true)
                }
                
                Log.d(TAG, "Starting audio stream to $serverIp:$serverPort")
                
                // Start capturing and streaming audio
                audioCapture?.startCapture()
                    ?.catch { e ->
                        Log.e(TAG, "Audio capture error: ${e.message}")
                        withContext(Dispatchers.Main) {
                            onError?.invoke("Audio capture failed: ${e.message}")
                        }
                    }
                    ?.collect { audioData ->
                        // Send audio data to server
                        networkClient?.sendAudioData(audioData)
                        
                        // Update packet count periodically
                        val packetsSent = networkClient?.getPacketsSent() ?: 0
                        if (packetsSent % 50 == 0) {
                            withContext(Dispatchers.Main) {
                                onPacketsSent?.invoke(packetsSent)
                            }
                        }
                    }
                    
            } catch (e: Exception) {
                Log.e(TAG, "Streaming error: ${e.message}")
                withContext(Dispatchers.Main) {
                    onError?.invoke("Streaming error: ${e.message}")
                }
            } finally {
                isStreaming = false
                withContext(Dispatchers.Main) {
                    onStreamingStateChanged?.invoke(false)
                }
            }
        }
    }
    
    /**
     * Stop audio streaming
     */
    fun stopStreaming() {
        streamingJob?.cancel()
        streamingJob = null
        audioCapture?.stopCapture()
        networkClient?.disconnect()
        isStreaming = false
        onStreamingStateChanged?.invoke(false)
    }
    
    /**
     * Check if currently streaming
     */
    fun isStreaming(): Boolean = isStreaming
    
    /**
     * Get connection info
     */
    fun getConnectionInfo(): Pair<String, Int> = Pair(serverIp, serverPort)
    
    /**
     * Create notification channel (required for Android 8+)
     */
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Audio Streaming",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows when audio is being streamed"
                setShowBadge(false)
            }
            
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }
    
    /**
     * Create foreground notification
     */
    private fun createNotification(): Notification {
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        val stopIntent = Intent(this, AudioStreamService::class.java).apply {
            action = ACTION_STOP
        }
        
        val stopPendingIntent = PendingIntent.getService(
            this, 1, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("PulseLink Streaming")
            .setContentText("Streaming audio to $serverIp")
            .setSmallIcon(R.drawable.icon)
            .setContentIntent(pendingIntent)
            .addAction(
                android.R.drawable.ic_media_pause,
                "Stop",
                stopPendingIntent
            )
            .setOngoing(true)
            .build()
    }
}
