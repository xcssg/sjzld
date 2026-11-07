# 左方雷达 —— 安卓 APP 工程

## 目录结构

```
android/
├── app/
│   ├── build.gradle                    # 应用模块构建脚本（AGP 8.13.2）
│   ├── proguard-rules.pro
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── assets/
│       │   ├── frida-hook.js           # Frida 密钥捕获脚本
│       │   └── radar/                  # 前端资源（运行 sync_assets.sh 生成）
│       ├── cpp/
│       │   ├── CMakeLists.txt
│       │   └── decrypt.c               # NDK 解密模块（纯 C，可编译）
│       ├── java/com/zuofang/radar/
│       │   ├── MainActivity.kt         # WebView 壳 + VPN 授权
│       │   ├── CaptureVpnService.kt    # VpnService 抓包
│       │   ├── LocalHttpServer.kt      # 本地 HTTP 供前端资源
│       │   └── ParserBridge.kt         # NDK 桥接 + JSONL 封装
│       └── res/
├── build.gradle
├── settings.gradle
├── gradle.properties
├── gradle/wrapper/gradle-wrapper.properties
├── scripts/sync_assets.sh              # 前端资源同步脚本
├── requirements-android.txt
└── .github/workflows/build-apk.yml     # GitHub Actions 打包
```

## 版本（2026-11 实测最新稳定版）

| 组件      | 版本    |
|-----------|---------|
| Gradle    | 8.13    |
| AGP       | 8.13.2  |
| Kotlin    | 2.1.21  |
| compileSdk| 35      |
| minSdk    | 26      |
| NDK       | 27.x（CMake 3.22.1）|

Python 依赖（若用 Chaquopy）：numpy 2.5.4、websockets 17.4、protobuf 7.36.2

## 快速开始

### 1. 同步前端资源（必须）
```bash
# 在 雷达开发 目录下执行
bash android/scripts/sync_assets.sh
```
这会把 `client/runtime/ErCore/web/`（含 366MB 地图）和
`client/ui/original_radar_page.html` 拷进 `assets/radar/`。

### 2. 生成 gradlew（首次）
```bash
cd android
gradle wrapper --gradle-version 8.13
```

### 3. 本地打包
```bash
cd android
./gradlew assembleDebug
# 产物: app/build/outputs/apk/debug/app-debug.apk
```

### 4. 安装验证
```bash
adb install app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.zuofang.radar/.MainActivity
```

## GitHub Actions 打包

1. 初始化仓库并推送：
```bash
cd android
git init
git lfs track "app/src/main/assets/radar/**/*.glb"
git add .
git commit -m "左方雷达安卓版"
git remote add origin <你的仓库地址>
git push -u origin main
```

2. 打开 GitHub 仓库 → Actions → Build APK → Run workflow
3. 跑完在 Artifacts 下载「左方雷达-APK.zip」

> 注意：地图 GLB 单文件最大 99MB，走 Git LFS；若仓库超 2GB，
> 把地图资源放 release 附件或改用 LFS 配额。

## 移植映射

| Windows 组件            | 安卓等价物         | 状态           |
|-------------------------|-------------------|----------------|
| WinDivert 抓包          | VpnService        | 已实现         |
| UDP 去混淆(XOR流密码)    | NDK decrypt.c     | ✅ 已实现（已还原验证）|
| codec 解析层(引擎包→坐标) | 还原 Python / Kotlin重写 | 待还原 |
| 浏览器雷达页            | WebView + assets  | 已实现         |

## 解密真相（重要）

**不需要 root、不需要逆向 exe。** UDP 解密是 `s2c_dec.py` 里的 XOR 流密码：

```
P[i] = C[i] ^ C[i-1] ^ K[i % 512]   （512 字节循环表）
```

已从 `runtime/vendor_pyc/s2c_dec.pyc` 逐字还原并验证通过：
- `android/python/s2c_dec.py`（Python 还原版）
- `decrypt.c`（NDK C 实现：loadTable / decryptUdp / recoverTable）

K 表可自动从裸抓包恢复（`recover_table` 众数投票），无需预置、无需 root。
详见 `docs/解密真相.md`。

## 剩余工作

把 `runtime/vendor_pyc/codec/` 下 8 个解析模块（engine_packet、engine_bunch、
bitstream、bunch、packet、object_desc、rep_layout、engine_stream）也还原成
可读源码或 Kotlin 重写，即可完成「明文引擎包 → 玩家坐标」的解析。
