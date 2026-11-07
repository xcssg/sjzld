#!/bin/bash
# 左方雷达 —— 前端资源同步脚本
# 把 client/runtime/ErCore/web/ 和 client/ui/ 的资源拷进 android/assets/radar/
# 用法：在 雷达开发 目录下执行  bash android/scripts/sync_assets.sh
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"          # 雷达开发
CLIENT="$ROOT/client"
DEST="$ROOT/android/app/src/main/assets/radar"

echo "[1/4] 创建目标目录: $DEST"
mkdir -p "$DEST"

echo "[2/4] 拷贝前端 web 资源 (runtime/ErCore/web/)"
if [ -d "$CLIENT/runtime/ErCore/web" ]; then
    cp -a "$CLIENT/runtime/ErCore/web/." "$DEST/"
else
    echo "  ! 未找到 runtime/ErCore/web，跳过"
fi

echo "[3/4] 拷贝雷达页 (ui/original_radar_page.html)"
if [ -f "$CLIENT/ui/original_radar_page.html" ]; then
    cp -a "$CLIENT/ui/original_radar_page.html" "$DEST/"
else
    echo "  ! 未找到 original_radar_page.html，跳过"
fi

echo "[4/4] 拷贝图标"
if [ -f "$CLIENT/ui/左方雷达.ico" ]; then
    cp -a "$CLIENT/ui/左方雷达.ico" "$DEST/"
fi

echo ""
echo "完成。资源目录大小:"
du -sh "$DEST"
echo ""
echo "下一步:"
echo "  1) 在 android/ 目录生成 gradlew:  gradle wrapper --gradle-version 8.13"
echo "  2) git init && git add . && git commit && git push 到 GitHub"
echo "  3) GitHub Actions 点 Run workflow 打包"
