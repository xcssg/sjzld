/*
 * 左方雷达 —— S2C UDP 去混淆模块（NDK，纯 C，无外部依赖）
 *
 * 真正的「解密」不是 AES、不是逆向 exe，而是 s2c_dec.py 里的
 * XOR 流密码（密文反馈）：
 *
 *     P[i] = C[i] ^ C[i-1] ^ K[i % 512]
 *     C[-1] = 0，每条 UDP 记录独立重置
 *
 * K 表：512 字节，按连接实例化。有两种来源：
 *   1) 已知表：loadTable() 直接加载（.bin 原始字节）
 *   2) 无表：从裸抓包自动恢复（recoverTable() 众数投票），
 *      等价 s2c_dec.py 的 recover_table()，无需 root、无需逆向 exe。
 *
 * 还原后即标准 UE4 引擎包，交给上层 codec 管线解析玩家坐标。
 */

#include <jni.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>

#define TABLE_LEN 512

/* 当前连接的 512 字节 K 表；全 0 表示「未加载」 */
static uint8_t key_table[TABLE_LEN] = {0};
static int table_loaded = 0;

/* ============ JNI: 加载已知 K 表 ============ */
JNIEXPORT void JNICALL
Java_com_zuofang_radar_ParserBridge_loadTable(JNIEnv *env, jobject thiz, jbyteArray table) {
    if (table == NULL) return;
    jsize n = (*env)->GetArrayLength(env, table);
    if (n != TABLE_LEN) return;                      /* 必须 512 字节 */
    (*env)->GetByteArrayRegion(env, table, 0, TABLE_LEN, (jbyte *) key_table);
    table_loaded = 1;
}

/* ============ JNI: 单条 UDP 记录去混淆 ============ */
JNIEXPORT jbyteArray JNICALL
Java_com_zuofang_radar_ParserBridge_decryptUdp(JNIEnv *env, jobject thiz, jbyteArray payload) {
    if (payload == NULL) return NULL;
    jsize n = (*env)->GetArrayLength(env, payload);
    jbyteArray result = (*env)->NewByteArray(env, n);
    if (result == NULL) return NULL;

    jbyte *src = (*env)->GetByteArrayElements(env, payload, 0);
    jbyte *dst = (*env)->GetByteArrayElements(env, result, 0);
    if (src == NULL || dst == NULL) {
        if (src) (*env)->ReleaseByteArrayElements(env, payload, src, 0);
        if (dst) (*env)->ReleaseByteArrayElements(env, result, dst, 0);
        return result;
    }

    if (table_loaded) {
        uint8_t prev = 0;
        for (jsize i = 0; i < n; i++) {
            uint8_t c = (uint8_t) src[i];
            uint8_t p = (uint8_t)(c ^ prev ^ key_table[i & 511]);
            dst[i] = (jbyte) p;
            prev = c;          /* 反馈用原始密文 c，不是明文 */
        }
    } else {
        /* 无表：原样透传（上层按明文解析失败处理），保证游戏流量不断 */
        memcpy(dst, src, (size_t) n);
    }

    (*env)->ReleaseByteArrayElements(env, payload, src, 0);
    (*env)->ReleaseByteArrayElements(env, result, dst, 0);
    return result;
}

/* ============ JNI: 从裸抓包恢复 K 表（众数投票） ============ */
/*
 * 等价 s2c_dec.py 的 recover_table()。
 * 输入：多条密文 UDP 记录的拼接（每条长度存于 lengths[]）。
 * 对每个位置 i 统计 (C[i] ^ C[i-1]) 的众数，即为 K[i%512]。
 * 需要足够多的样本（每条包越多、样本越多，恢复越准）。
 */
JNIEXPORT jboolean JNICALL
Java_com_zuofang_radar_ParserBridge_recoverTable(
        JNIEnv *env, jobject thiz,
        jbyteArray blob, jintArray lengths, jint minCount, jint maxLen) {

    if (blob == NULL || lengths == NULL) return JNI_FALSE;

    jsize blob_len = (*env)->GetArrayLength(env, blob);
    jsize n_datagrams = (*env)->GetArrayLength(env, lengths);
    if (blob_len <= 0 || n_datagrams <= 0) return JNI_FALSE;

    jbyte *blob = (*env)->GetByteArrayElements(env, blob, 0);
    jint *lens = (*env)->GetIntArrayElements(env, lengths, 0);
    if (blob == NULL || lens == NULL) {
        if (blob) (*env)->ReleaseByteArrayElements(env, blob, blob, 0);
        if (lens) (*env)->ReleaseIntArrayElements(env, lengths, lens, 0);
        return JNI_FALSE;
    }

    if (minCount < 1) minCount = 1;
    if (maxLen < 1) maxLen = 1024;

    /* 每个表位置的候选值计数（256 种可能字节值） */
    int cnt[TABLE_LEN][256];
    memset(cnt, 0, sizeof(cnt));

    /* 累加每条数据报的 (C[i] ^ C[i-1]) */
    jsize offset = 0;
    for (jsize d = 0; d < n_datagrams; d++) {
        jint len = lens[d];
        if (len <= 0 || len > maxLen) { offset += len; continue; }
        uint8_t prev = 0;
        for (jint i = 0; i < len; i++) {
            uint8_t b = (uint8_t) blob[offset + i];
            uint8_t v = (uint8_t)(b ^ prev);
            cnt[i & 511][v]++;
            prev = b;
        }
        offset += len;
    }

    /* 每个位置取众数；若众数出现次数 < minCount 则失败 */
    uint8_t table[TABLE_LEN];
    for (int j = 0; j < TABLE_LEN; j++) {
        int best_v = 0, best_c = -1;
        for (int v = 0; v < 256; v++) {
            if (cnt[j][v] > best_c) { best_c = cnt[j][v]; best_v = v; }
        }
        if (best_c < minCount) {
            (*env)->ReleaseByteArrayElements(env, blob, blob, 0);
            (*env)->ReleaseIntArrayElements(env, lengths, lens, 0);
            return JNI_FALSE;       /* 样本不足 */
        }
        table[j] = (uint8_t) best_v;
    }

    memcpy(key_table, table, TABLE_LEN);
    table_loaded = 1;

    (*env)->ReleaseByteArrayElements(env, blob, blob, 0);
    (*env)->ReleaseIntArrayElements(env, lengths, lens, 0);
    return JNI_TRUE;
}

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) vm; (void) reserved;
    return JNI_VERSION_1_6;
}
