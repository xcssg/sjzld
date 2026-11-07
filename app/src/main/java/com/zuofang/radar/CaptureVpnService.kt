package com.zuofang.radar

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import java.io.FileInputStream
import java.io.FileOutputStream

/**
 * 左方雷达 —— VPN 抓包服务（替代 Windows 版 WinDivert）
 *
 * 通过 VpnService 建立系统级隧道，读取所有进出设备的 UDP 流量，
 * 经 NDK 解密后推给 ParserBridge，再把原始包立即回写（reinject），
 * 保证游戏网络不断流。
 */
class CaptureVpnService : VpnService() {

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val vpn = establishVpn() ?: return START_NOT_STICKY
        startForeground(NOTIFICATION_ID, buildNotification())
        Thread { pump(vpn) }.start()
        return START_STICKY
    }

    private fun establishVpn(): ParcelFileDescriptor? {
        return try {
            Builder()
                .setSession(getString(R.string.app_name))
                .addAddress("10.8.0.2", 24)
                .addRoute("0.0.0.0", 0)
                .addDnsServer("8.8.8.8")
                .setMtu(1500)
                .setBlocking(true)
                .establish()
        } catch (_: Exception) {
            null
        }
    }

    private fun buildNotification(): Notification {
        createChannel()
        val pi = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.vpn_title))
            .setContentText(getString(R.string.vpn_text))
            .setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= 26) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.vpn_notify_channel_name),
                    NotificationManager.IMPORTANCE_LOW
                )
            )
        }
    }

    private fun pump(vpn: ParcelFileDescriptor) {
        val input = FileInputStream(vpn.fileDescriptor)
        val output = FileOutputStream(vpn.fileDescriptor)
        val buf = ByteArray(65535)
        try {
            while (true) {
                val n = input.read(buf)
                if (n <= 0) break
                val pkt = buf.copyOf(n)
                val ipHdrLen = (pkt[0].toInt() and 0x0F) * 4
                if (pkt.size > ipHdrLen + 8 && (pkt[9].toInt() and 0xFF) == 17) {
                    // UDP 包
                    val srcPort = ((pkt[ipHdrLen].toInt() and 0xFF) shl 8) or (pkt[ipHdrLen + 1].toInt() and 0xFF)
                    val dstPort = ((pkt[ipHdrLen + 2].toInt() and 0xFF) shl 8) or (pkt[ipHdrLen + 3].toInt() and 0xFF)
                    val payload = pkt.copyOfRange(ipHdrLen + 8, pkt.size)
                    val decrypted = ParserBridge.decryptUdp(payload)
                    ParserBridge.push(srcPort, dstPort, decrypted)
                }
                output.write(pkt)   // 原样回写，保证流量不断
                output.flush()
            }
        } catch (_: Exception) {
        } finally {
            try { input.close() } catch (_: Exception) {}
            try { output.close() } catch (_: Exception) {}
        }
    }

    companion object {
        const val NOTIFICATION_ID = 1
        const val CHANNEL_ID = "radar_capture"
    }
}
