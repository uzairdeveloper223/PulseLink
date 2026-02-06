package dev.uzair.pulselink.network

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * UDP Client for streaming audio to the Linux server
 */
class NetworkClient {
    
    companion object {
        private const val TAG = "NetworkClient"
        private const val MAX_PACKET_SIZE = 4096
    }
    
    private var socket: DatagramSocket? = null
    private var serverAddress: InetAddress? = null
    private var serverPort: Int = 5555
    
    private val isConnected = AtomicBoolean(false)
    private val sequenceNumber = AtomicInteger(0)
    
    var onConnectionStateChanged: ((Boolean) -> Unit)? = null
    var onError: ((String) -> Unit)? = null
    
    /**
     * Connect to the server
     */
    suspend fun connect(ip: String, port: Int): Boolean = withContext(Dispatchers.IO) {
        try {
            disconnect()
            
            serverAddress = InetAddress.getByName(ip)
            serverPort = port
            socket = DatagramSocket()
            socket?.soTimeout = 5000
            
            isConnected.set(true)
            sequenceNumber.set(0)
            
            Log.d(TAG, "Connected to $ip:$port")
            onConnectionStateChanged?.invoke(true)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Connection failed: ${e.message}")
            onError?.invoke("Failed to connect: ${e.message}")
            false
        }
    }
    
    /**
     * Disconnect from the server
     */
    fun disconnect() {
        try {
            socket?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Error closing socket: ${e.message}")
        }
        socket = null
        serverAddress = null
        isConnected.set(false)
        onConnectionStateChanged?.invoke(false)
    }
    
    /**
     * Send audio data to the server
     * Packet format: [4 bytes sequence number][audio data]
     */
    suspend fun sendAudioData(audioData: ByteArray): Boolean = withContext(Dispatchers.IO) {
        if (!isConnected.get() || socket == null || serverAddress == null) {
            return@withContext false
        }
        
        try {
            // Create packet with sequence number header
            val seqNum = sequenceNumber.getAndIncrement()
            val buffer = ByteBuffer.allocate(4 + audioData.size)
            buffer.putInt(seqNum)
            buffer.put(audioData)
            
            val packetData = buffer.array()
            val packet = DatagramPacket(
                packetData,
                packetData.size,
                serverAddress,
                serverPort
            )
            
            socket?.send(packet)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Send failed: ${e.message}")
            if (e.message?.contains("Network is unreachable") == true ||
                e.message?.contains("Host is unreachable") == true) {
                onError?.invoke("Server unreachable")
                disconnect()
            }
            false
        }
    }
    
    /**
     * Check if connected
     */
    fun isConnected(): Boolean = isConnected.get()
    
    /**
     * Get current sequence number (for diagnostics)
     */
    fun getPacketsSent(): Int = sequenceNumber.get()
}
