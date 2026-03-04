#!/bin/bash
# Richman Skill — ClawHub 发布脚本
# 
# 使用方法：
# 1. 先在 GitHub 上创建一个名为 richman-skill 的公开仓库（不要初始化 README）
# 2. 把本目录下的文件复制到你想用的本地目录
# 3. 修改下面的 GITHUB_USER 为你的 GitHub 用户名
# 4. 运行这个脚本
#
# 或者手动执行下面的命令。

GITHUB_USER="你的GitHub用户名"  # ← 改成你的

echo "=== Step 1: 初始化 Git 仓库 ==="
git init
git add SKILL.md README.md LICENSE .gitignore
git commit -m "feat: richman-skill v1.0.0 — A股投研观点分析助手"

echo ""
echo "=== Step 2: 推送到 GitHub ==="
git branch -M main
git remote add origin "https://github.com/${GITHUB_USER}/richman-skill.git"
git push -u origin main

echo ""
echo "=== Step 3: 发布到 ClawHub ==="
echo "请确认你已经登录 clawhub（如果没有，先运行 clawhub login）"
clawhub publish ./

echo ""
echo "=== Step 4: 验证发布 ==="
clawhub search richman-skill

echo ""
echo "✅ 完成！任何人现在可以通过以下方式安装："
echo "   clawhub install richman-skill"
echo ""
echo "   或者在 OpenClaw 对话中粘贴："
echo "   https://github.com/${GITHUB_USER}/richman-skill"
