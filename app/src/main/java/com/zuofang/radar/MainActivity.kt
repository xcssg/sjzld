package com.zuofang.radar

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient

/**
 * 左方雷达 —— 主界面
 *
 * 启动本地 HTTP 服务，把 assets/radar 的前端雷达页加载进 WebView，
 * 并请求 VPN 授权开始抓包。
 */
class MainActivity : Activity() {

    private lateinit var server: LocalHttpServer

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        server = LocalHttpServer(this, 17891)
        server.start()

        val web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.allowFileAccess = true
        web.settings.domStorageEnabled = true
        web.settings.allowContentAccess = true
        web.webViewClient = WebViewClient()
        web.loadUrl("http://127.0.0.1:17891/radar")
        setContentView(web)

        requestVpn()
    }

    private fun requestVpn() {
        val intent = VpnService.prepare(this)
        if (intent != null) {
            startActivityForResult(intent, VPN_REQUEST)
        } else {
            startService(Intent(this, CaptureVpnService::class.java))
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == VPN_REQUEST && resultCode == RESULT_OK) {
            startService(Intent(this, CaptureVpnService::class.java))
        }
    }

    override fun onDestroy() {
        server.stop()
        super.onDestroy()
    }

    companion object {
        private const val VPN_REQUEST = 100
    }
}
