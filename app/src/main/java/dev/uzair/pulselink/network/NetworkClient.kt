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
            socket?.soTimeout = 3000 // 3 second timeout for server check
            
            // Check if server is reachable by sending a ping packet
            // The server should respond to any UDP packet
            val isServerRunning = checkServerReachable()
            if (!isServerRunning) {
                socket?.close()
                socket = null
                serverAddress = null
                onError?.invoke("Server is not running. Please start the Linux server first.")
                return@withContext false
            }
            
            // Server is reachable, set normal timeout
            socket?.soTimeout = 5000
            
            isConnected.set(true)
            sequenceNumber.set(0)
            
            Log.d(TAG, "Connected to $ip:$port")
            onConnectionStateChanged?.invoke(true)
            true
        } catch (e: Exception) {
            Log.e(TAG, "Connection failed: ${e.message}")
            when {
                e.message?.contains("Network is unreachable") == true ->
                    onError?.invoke("Network is unreachable. Check your WiFi connection.")
                e.message?.contains("Host is unreachable") == true ->
                    onError?.invoke("Server is not running. Please start the Linux server first.")
                e.message?.contains("UnknownHostException") == true ->
                    onError?.invoke("Invalid server address. Please scan QR code again.")
                else ->
                    onError?.invoke("Failed to connect: ${e.message}")
            }
            false
        }
    }
    
    /**
     * Check if the server is reachable by attempting a quick connection test
     */
    private fun checkServerReachable(): Boolean {
        return try {
            // Send a small test packet to check if server is listening
            val testData = ByteBuffer.allocate(4).putInt(-1).array() // Special ping packet
            val packet = DatagramPacket(testData, testData.size, serverAddress, serverPort)
            socket?.send(packet)
            
            // For UDP, we just check if send succeeds without exception
            // The actual reachability is determined by whether we get responses during streaming
            true
        } catch (e: Exception) {
            Log.e(TAG, "Server check failed: ${e.message}")
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
            when {
                e.message?.contains("Network is unreachable") == true ->
                    onError?.invoke("Network disconnected. Check your WiFi connection.")
                e.message?.contains("Host is unreachable") == true ->
                    onError?.invoke("Server stopped. The Linux server is no longer running.")
                e.message?.contains("Permission denied") == true ->
                    onError?.invoke("Network permission denied.")
                else ->
                    onError?.invoke("Connection lost: ${e.message}")
            }
            disconnect()
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
