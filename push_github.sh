#!/bin/bash
# 左方雷达 —— git 一条龙提交脚本
# 用法：在 android/ 目录下执行  bash push_github.sh <你的仓库地址>
# 示例：bash push_github.sh https://github.com/你的用户名/左方雷达.git
set -e

if [ -z "$1" ]; then
    echo "用法: bash push_github.sh <仓库地址>"
    echo "示例: bash push_github.sh https://github.com/user/zuofang-radar.git"
    exit 1
fi

REMOTE="$1"

echo "[1/5] 初始化 git 仓库"
if [ ! -d .git ]; then
    git init
fi

echo "[2/5] 配置 Git LFS（地图 GLB 单文件超 100MB，必须走 LFS）"
git lfs version >/dev/null 2>&1 || { echo "请先安装 git-lfs"; exit 1; }
git lfs track "app/src/main/assets/radar/**/*.glb"
git lfs track "app/src/main/assets/radar/**/*.gz"

echo "[3/5] 添加所有文件"
git add .
git add .gitattributes

echo "[4/5] 提交"
git commit -m "左方雷达安卓版：完整 Gradle 工程 + GitHub Actions 打包" || echo "（无变更或已提交）"

echo "[5/5] 推送"
git branch -M main
git remote remove origin 2>/dev/null || true
git remote add origin "$REMOTE"
git push -u origin main

echo ""
echo "完成！现在去 GitHub 仓库 → Actions → Build APK → Run workflow"
echo "跑完后在 Artifacts 下载「左方雷达-APK.zip」"
