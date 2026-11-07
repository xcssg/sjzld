package com.zuofang.radar

import android.util.Base64
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicLong

/**
 * 左方雷达 —— 解析桥接层
 *
 * 职责：
 *  1. JNI 调用 NDK 去混淆模块（XOR 流密码，见 s2c_dec.py）
 *     - loadTable()    加载已知 512 字节 K 表
 *     - recoverTable() 从裸抓包自动恢复 K 表（无需 root/逆向）
 *     - decryptUdp()   单条 UDP 记录去混淆：P[i] = C[i]^C[i-1]^K[i%512]
 *  2. 把去混淆后的明文包装成 gateway_parser.py 约定的 JSONL 事件，
 *     交给本地解析管线（本地 HTTP 服务 / Kotlin 解析器消费）
 */
object ParserBridge {

    private val seq = AtomicLong(0)
    private val queue = ConcurrentLinkedQueue<ByteArray>()

    init {
        System.loadLibrary("decrypt")
    }

    /** 加载已知 512 字节 XOR 表（有现成表时用） */
    external fun loadTable(table: ByteArray)

    /** 从裸抓包自动恢复 512 字节表（无表时用，等价 s2c_dec.recover_table） */
    external fun recoverTable(blob: ByteArray, lengths: IntArray, minCount: Int, maxLen: Int): Boolean

    /** 单条 UDP 记录去混淆，返回明文 */
    external fun decryptUdp(payload: ByteArray): ByteArray

    /** 抓到的明文包入队，供解析器消费 */
    fun push(srcPort: Int, dstPort: Int, payload: ByteArray) {
        if (payload.isEmpty()) return
        val n = seq.getAndIncrement()
        val b64 = Base64.encodeToString(payload, Base64.NO_WRAP)
        val jsonl = buildString {
            append("""{"type":"udp_plaintext","sequence":$n,""")
            append(""""data":{"direction":"down","timestampMs":${System.currentTimeMillis()},""")
            append(""""payloadBase64":"$b64","payloadLength":${payload.size},""")
            append(""""local":"10.8.0.1:$dstPort","remote":"10.8.0.2:$srcPort","epoch":1}}}""")
        }
        queue.add(jsonl.toByteArray(Charsets.UTF_8))
    }

    fun poll(): ByteArray? = queue.poll()

    /** 收集样本自动恢复表：把 buffer 按 datagram 长度切分喂给 recoverTable */
    fun autoRecover(samples: List<ByteArray>, minCount: Int = 8): Boolean {
        if (samples.isEmpty()) return false
        val lens = IntArray(samples.size) { samples[it].size }
        val total = lens.sum()
        val blob = ByteArray(total)
        var off = 0
        for (s in samples) {
            System.arraycopy(s, 0, blob, off, s.size)
            off += s.size
        }
        return recoverTable(blob, lens, minCount, 1024)
    }
}
