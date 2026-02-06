package dev.uzair.pulselink.audio

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.app.ActivityCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import kotlin.coroutines.coroutineContext
import kotlin.math.sqrt

/**
 * Audio capture utility using AudioRecord
 * Captures PCM audio from the microphone
 */
class AudioCapture(private val context: Context) {
    
    companion object {
        private const val TAG = "AudioCapture"
        
        // Audio settings optimized for low latency streaming
        const val SAMPLE_RATE = 48000  // Match server's expected rate
        const val CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
        const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        const val FRAME_SIZE = 960  // 20ms at 48kHz (matches Opus)
        
        // Buffer size calculation
        val BUFFER_SIZE: Int = maxOf(
            AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_CONFIG, AUDIO_FORMAT),
            FRAME_SIZE * 2 * 2  // frame size * 2 bytes per sample * 2 frames
        )
    }
    
    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    
    var onAudioLevel: ((Float) -> Unit)? = null
    
    /**
     * Check if recording permission is granted
     */
    fun hasPermission(): Boolean {
        return ActivityCompat.checkSelfPermission(
            context,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }
    
    /**
     * Start audio capture and return a flow of audio buffers
     */
    fun startCapture(): Flow<ByteArray> = flow {
        if (!hasPermission()) {
            Log.e(TAG, "Recording permission not granted")
            return@flow
        }
        
        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                CHANNEL_CONFIG,
                AUDIO_FORMAT,
                BUFFER_SIZE
            )
            
            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord failed to initialize")
                return@flow
            }
            
            audioRecord?.startRecording()
            isRecording = true
            Log.d(TAG, "Audio capture started")
            
            val buffer = ByteArray(FRAME_SIZE * 2)  // 16-bit samples = 2 bytes each
            
            while (coroutineContext.isActive && isRecording) {
                val bytesRead = audioRecord?.read(buffer, 0, buffer.size) ?: -1
                
                if (bytesRead > 0) {
                    // Calculate audio level for visualization
                    calculateAudioLevel(buffer, bytesRead)
                    
                    // Emit the audio data
                    emit(buffer.copyOf(bytesRead))
                } else if (bytesRead < 0) {
                    Log.e(TAG, "AudioRecord read error: $bytesRead")
                    break
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Audio capture error: ${e.message}")
        } finally {
            stopCapture()
        }
    }.flowOn(Dispatchers.IO)
    
    /**
     * Stop audio capture
     */
    fun stopCapture() {
        isRecording = false
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping audio: ${e.message}")
        }
        audioRecord = null
        Log.d(TAG, "Audio capture stopped")
    }
    
    /**
     * Calculate RMS audio level for visualization
     */
    private fun calculateAudioLevel(buffer: ByteArray, length: Int) {
        var sum = 0.0
        val numSamples = length / 2
        
        for (i in 0 until numSamples) {
            // Convert two bytes to short (little-endian)
            val sample = (buffer[i * 2].toInt() and 0xFF) or
                        (buffer[i * 2 + 1].toInt() shl 8)
            sum += sample * sample
        }
        
        val rms = sqrt(sum / numSamples)
        val level = (rms / 32768.0).toFloat().coerceIn(0f, 1f)
        
        onAudioLevel?.invoke(level)
    }
    
    /**
     * Check if currently recording
     */
    fun isRecording(): Boolean = isRecording
}
