# wb-checkin-custom

WorkBuddy批量签到 定制版自动构建仓库。
官方 workbuddy-one 每发新版本，GitHub Actions 自动打补丁（改名 + 换 logo）并发布定制包到本仓库 Release。

- `custom_build.py` — 定制补丁 + 构建脚本
- `logo.png` — 定制 logo 素材
- `.github/workflows/custom-release.yml` — 自动构建流水线
