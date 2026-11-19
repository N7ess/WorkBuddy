#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WorkBuddy批量签到 定制构建脚本
流程: 拉取官方源码(指定 tag) -> 自动打定制补丁(改名+换logo) -> 编译 -> 打 zip 更新包
用法:
  python custom_build.py                 # 构建官方最新 release 版本
  python custom_build.py --tag v1.0.17   # 构建指定版本
  python custom_build.py --zip-only tag  # 只打 zip(已有 exe)
依赖: git, Go 1.22+ (go/bin 下含 go-winres), Python 3 + Pillow
"""
import argparse, base64, io, os, re, shutil, subprocess, sys, urllib.request

# Windows Runner 默认 cp1252 输出编码，打印中文会炸，强制 UTF-8
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
UPSTREAM_REPO = "https://github.com/3155498108/workbuddy-one"
BUILD_DIR = os.path.join(HERE, "build")
DIST_DIR = os.path.join(HERE, "dist")
GO_BIN = os.path.join(os.path.expanduser("~"),
    r".workbuddy\binaries\python\..\..")  # 占位, 下面会解析
APP_NAME = "WorkBuddy批量签到"
BRAND_OLD = "WorkBuddy 管家"

def find_go():
    # 优先本工作区工具链, 其次系统 PATH
    cand = os.path.join(HERE, "..", "go", "bin", "go.exe")
    cand = os.path.abspath(cand)
    if os.path.exists(cand):
        return cand
    return "go"

def find_winres():
    cand = os.path.join(HERE, "..", "go", "bin", "go-winres.exe")
    cand = os.path.abspath(cand)
    if os.path.exists(cand):
        return cand
    return "go-winres"

def latest_tag():
    req = urllib.request.Request(UPSTREAM_REPO + "/releases/latest", method="HEAD")
    with urllib.request.urlopen(req) as r:
        final = r.geturl()          # 302 后的最终 URL: .../tag/vX.Y.Z
    return final.rstrip("/").split("/tag/")[-1]

def run(cmd, cwd=None, env=None):
    print("+", " ".join(cmd))
    e = os.environ.copy()
    e.setdefault("GOPROXY", "https://goproxy.cn,direct")
    e.setdefault("GOSUMDB", "sum.golang.google.cn")
    if env: e.update(env)
    subprocess.run(cmd, cwd=cwd, env=e, check=True)

def fetch_source(tag):
    src = os.path.join(BUILD_DIR, "src")
    if os.path.exists(src):
        shutil.rmtree(src, ignore_errors=True)
    os.makedirs(BUILD_DIR, exist_ok=True)
    run(["git", "clone", "--depth", "1", "--branch", tag, UPSTREAM_REPO, src])
    return src

def make_icon(src_dir):
    from PIL import Image
    logo = Image.open(os.path.join(HERE, "logo.png")).convert("RGBA")
    px = logo.load()
    w, h = logo.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r > 242 and g > 242 and b > 242:
                px[x, y] = (r, g, b, 0)
    logo = logo.crop(logo.getbbox())
    side = max(logo.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2))
    wbone = os.path.join(src_dir, "cmd", "wbone")
    sq.save(os.path.join(wbone, "app.ico"), format="ICO",
            sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
    small = sq.resize((96, 96), Image.LANCZOS)
    b64 = io.BytesIO(); small.save(b64, format="PNG")
    return base64.b64encode(b64.getvalue()).decode()

def patch_ui(src_dir, b64):
    f = os.path.join(src_dir, "cmd", "wbone", "ui.html")
    html = open(f, encoding="utf-8").read()
    img_tag = '<img src="data:image/png;base64,' + b64 + \
              '" style="width:100%;height:100%;display:block;border-radius:9px" alt="">'
    favicon = '<link rel="icon" href="data:image/png;base64,' + b64 + '">'
    # 窗口标题
    html = re.sub(r"<title>[^<]*管家[^<]*</title>",
                  "<title>" + APP_NAME + "</title>\n" + favicon, html, count=1)
    # .logo 蓝色渐变底去掉
    html = re.sub(r"background:linear-gradient\(145deg,#3b7bf6,#2456c9\);",
                  "background:none;", html, count=1)
    # 侧栏 logo: 找 .logo div 内的第一个内联 svg
    m = re.search(r'<div class="logo">\s*(<svg.*?</svg>)', html, re.S)
    if m:
        html = html.replace(m.group(1), img_tag)
    # 侧栏标题
    html = html.replace("<b>" + BRAND_OLD + "</b>", "<b>" + APP_NAME + "</b>")
    open(f, "w", encoding="utf-8", newline="").write(html)

def make_syso(src_dir, tag):
    wbone = os.path.join(src_dir, "cmd", "wbone")
    run([find_winres(), "simply", "--arch", "amd64", "--out", "wbone",
         "--manifest", "gui", "--icon", "app.ico",
         "--product-name", APP_NAME,
         "--file-description", APP_NAME + "（定制版）",
         "--file-version", tag.lstrip("v"),
         "--product-version", tag.lstrip("v"),
         "--original-filename", APP_NAME + ".exe",
         "--copyright", "MIT License"], cwd=wbone)
    os.replace(os.path.join(wbone, "wbone_windows_amd64.syso"),
               os.path.join(wbone, "rsrc.syso"))

def build(src_dir, tag):
    exe = os.path.join(src_dir, APP_NAME + ".exe")
    run([find_go(), "build", "-trimpath", "-ldflags", "-H=windowsgui -s -w",
         "-o", exe, "./cmd/wbone"], cwd=src_dir)
    os.makedirs(DIST_DIR, exist_ok=True)
    # 更新器硬性要求: 资产名必须是 WorkBuddyOne-v<版本>-win64.zip,
    # 且 Release 的 tag 版本要比用户当前运行的官方版本高才触发更新,
    # 所以定制版统一在第 4 段 +1: v1.0.16 -> v1.0.16.1
    zipver = tag if tag.count(".") >= 3 else tag + ".1"
    zpath = os.path.join(DIST_DIR, "WorkBuddyOne-v" + zipver.lstrip("v") + "-win64.zip")
    import zipfile
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(exe, APP_NAME + ".exe")   # 包里只放一个 exe(更新器兜底逻辑靠它)
    print("更新包:", zpath)
    return zpath

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    tag = a.tag or latest_tag()
    print("== 构建版本:", tag)
    src = fetch_source(tag)
    b64 = make_icon(src)
    patch_ui(src, b64)
    make_syso(src, tag)
    build(src, tag)
    print("== 完成")

if __name__ == "__main__":
    main()
