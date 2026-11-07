package com.zuofang.radar

import android.content.Context
import android.content.res.AssetManager
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.ServerSocket

/**
 * 左方雷达 —— 本地 HTTP 服务
 *
 * 把 assets/radar/ 里的前端资源（original_radar_page.html、/vendor/、
 * /m3d/、/ui/ 等）通过 http://127.0.0.1:17891 提供给 WebView，
 * 端口与 Windows 版后端保持一致，前端 fetch() 路径无需改动。
 */
class LocalHttpServer(private val context: Context, private val port: Int = 17891) {

    private var server: ServerSocket? = null
    private var running = false

    fun start() {
        if (running) return
        running = true
        Thread {
            try {
                server = ServerSocket(port)
                while (running) {
                    val socket = server?.accept() ?: break
                    Thread { handle(socket) }.start()
                }
            } catch (_: Exception) {
            }
        }.start()
    }

    fun stop() {
        running = false
        try { server?.close() } catch (_: Exception) {}
        server = null
    }

    private fun handle(socket: java.net.Socket) {
        try {
            socket.getInputStream().use { input ->
                val request = readRequest(input)
                val path = parsePath(request)
                val (body, contentType) = loadAsset(path)
                val bytes = body
                val header = buildString {
                    append("HTTP/1.1 200 OK\r\n")
                    append("Content-Type: $contentType\r\n")
                    append("Content-Length: ${bytes.size}\r\n")
                    append("Connection: close\r\n")
                    append("Cache-Control: no-store\r\n")
                    append("\r\n")
                }.toByteArray(Charsets.UTF_8)
                socket.getOutputStream().use { out ->
                    out.write(header)
                    out.write(bytes)
                    out.flush()
                }
            }
        } catch (_: Exception) {
        } finally {
            try { socket.close() } catch (_: Exception) {}
        }
    }

    private fun readRequest(input: InputStream): String {
        val buf = ByteArray(4096)
        val sb = StringBuilder()
        var n = input.read(buf)
        while (n > 0) {
            sb.append(String(buf, 0, n, Charsets.UTF_8))
            if (sb.contains("\r\n\r\n")) break
            n = input.read(buf)
        }
        return sb.toString()
    }

    private fun parsePath(request: String): String {
        val line = request.substringBefore("\r\n")
        val parts = line.split(" ")
        if (parts.size < 2) return "/"
        var path = parts[1].substringBefore('?')
        if (path == "/") path = "/index.html"
        if (path == "/radar" || path == "/radar/") path = "/original_radar_page.html"
        return path
    }

    private fun loadAsset(path: String): Pair<ByteArray, String> {
        val asset = context.assets
        val clean = path.removePrefix("/")
        val contentType = when {
            clean.endsWith(".html") -> "text/html; charset=utf-8"
            clean.endsWith(".js") -> "application/javascript; charset=utf-8"
            clean.endsWith(".css") -> "text/css; charset=utf-8"
            clean.endsWith(".json") -> "application/json; charset=utf-8"
            clean.endsWith(".glb") -> "model/gltf-binary"
            clean.endsWith(".png") -> "image/png"
            clean.endsWith(".ico") -> "image/x-icon"
            else -> "application/octet-stream"
        }

        // assets/radar/ 为根目录映射
        val candidate = "radar/$clean"
        val stream = tryAsset(asset, candidate)
            ?: return (emptyArray<Byte>().toByteArray() to "text/plain")

        return (readAll(stream) to contentType)
    }

    private fun tryAsset(assets: AssetManager, path: String): InputStream? {
        return try { assets.open(path) } catch (_: Exception) { null }
    }

    private fun readAll(input: InputStream): ByteArray {
        val out = ByteArrayOutputStream()
        val buf = ByteArray(16384)
        var n = input.read(buf)
        while (n > 0) {
            out.write(buf, 0, n)
            n = input.read(buf)
        }
        return out.toByteArray()
    }
}
