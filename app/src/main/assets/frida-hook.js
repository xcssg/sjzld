/*
 * 左方雷达 —— Frida 密钥捕获脚本（root + Frida 注入游戏进程）
 *
 * 用途：hook 游戏进程的加密类/内存，捕获会话密钥，通过 send() 发回 App。
 * 用法（电脑上执行，手机需 root + USB 调试）：
 *
 *   adb push frida-server-17.26.1-android-arm64 /data/local/tmp/
 *   adb shell "chmod 755 /data/local/tmp/frida-server-17.26.1-android-arm64"
 *   adb shell "/data/local/tmp/frida-server-17.26.1-android-arm64 &"
 *   frida -U -f 游戏包名 -l frida-hook.js
 *
 * 密钥来源分两种情况（详见 android/docs/decrypt逆向填充指南.md）：
 *   情况 A：密钥在游戏 native 层固定偏移 → 用 readMemory 读（见下方 native_key）
 *   情况 B：密钥由 Java 层 Cipher.init 传入 → hook Cipher（见下方 java_key）
 */

function hexOf(buf) {
    var out = "";
    var bytes = new Uint8Array(buf);
    for (var i = 0; i < bytes.length; i++) {
        out += ("0" + bytes[i].toString(16)).slice(-2);
    }
    return out;
}

/* ============ 情况 A：native 层固定偏移读密钥 ============ */
// 填逆向拿到的实际值：
var NATIVE_SO_NAME = "lib游戏.so";   // 游戏的主 so 名
var KEY_OFFSET     = 0x0;            // 密钥在 so 内的偏移
var KEY_LEN        = 16;             // 密钥字节数

function native_key() {
    try {
        var base = Module.getBaseAddress(NATIVE_SO_NAME);
        if (!base) {
            send({ type: "error", value: "找不到 " + NATIVE_SO_NAME });
            return;
        }
        var keyPtr = base.add(KEY_OFFSET);
        var keyBytes = keyPtr.readByteArray(KEY_LEN);
        send({ type: "key", value: hexOf(keyBytes) });
    } catch (e) {
        send({ type: "error", value: String(e) });
    }
}

/* ============ 情况 B：Java 层 Cipher.init 捕获密钥 ============ */
function java_key() {
    Java.perform(function () {
        try {
            var Cipher = Java.use("javax.crypto.Cipher");
            Cipher.init.overload("int", "java.security.Key")
                .implementation = function (mode, key) {
                    var bytes = key.getEncoded();
                    send({ type: "key", value: hexOf(bytes) });
                    return this.init(mode, key);
                };
        } catch (e) {
            send({ type: "error", value: String(e) });
        }
    });
}

/* 默认执行：Java 层 hook + native 层读偏移同时尝试 */
Java.perform(function () {
    java_key();
});
native_key();
