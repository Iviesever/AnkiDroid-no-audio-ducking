# SPDX-License-Identifier: GPL-3.0-or-later
"""拉取上游后的补丁检查、构建参数和发布文件整理。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from datetime import datetime, timedelta, timezone
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PLAYER = Path("AnkiDroid/src/main/java/com/ichi2/anki/cardviewer/SoundTagPlayer.kt")
CERTIFICATE = "0a8ebeea7a7d04f21a737debedfb0b2ec439c84936e4bb69dc7f14894f0be42a"
APK_NAME = "AnkiDroid-no-audio-ducking-arm64-v8a.apk"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inputs_hash(root):
    result = hashlib.sha256()
    for pattern in ("patches/*.patch", "scripts/*.py", "tests/*.py", ".github/workflows/*.yml"):
        for path in sorted(root.glob(pattern)):
            result.update(path.relative_to(root).as_posix().encode() + b"\0")
            result.update(path.read_bytes())
    return result.hexdigest()


def needs_build(root, upstream_sha, force=False):
    state_file = root / "last-build.json"
    previous = json.loads(state_file.read_text()) if state_file.exists() else {}
    return force or previous.get("upstream_sha") != upstream_sha or previous.get("inputs_hash") != inputs_hash(root)


def record_check(root, now=None):
    now = now or datetime.now(timezone.utc)
    state_file = root / "last-build.json"
    state = json.loads(state_file.read_text())
    previous = datetime.fromisoformat(state.get("checked_at", state["built_at"]))
    if now - previous < timedelta(days=28):
        return False
    state["checked_at"] = now.isoformat()
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def output(**values):
    lines = "".join(f"{key}={str(value).lower() if isinstance(value, bool) else value}\n" for key, value in values.items())
    print(lines, end="")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(lines)


def verify_player(source):
    text = (source / PLAYER).read_text(encoding="utf-8")
    if re.search(r"requestAudioFocus|abandonAudioFocus|AudioFocusRequest|AUDIOFOCUS|AudioManagerCompat", text):
        raise RuntimeError("卡片音频中重新出现音频焦点代码，请调整补丁后再构建。")
    if not all(token in text for token in ("continuation.ensureActive()", "start()", "it.release()", "mediaPlayer?.stop()")):
        raise RuntimeError("音频播放器结构已改变，需要重新检查播放与资源释放逻辑。")


def apply_patch(root, source):
    patch = root / "patches/no-audio-ducking.patch"
    subprocess.run(["git", "-C", str(source), "apply", "--check", str(patch)], check=True)
    subprocess.run(["git", "-C", str(source), "apply", str(patch)], check=True)
    verify_player(source)


def runtime(source):
    versions = tomllib.loads((source / "gradle/libs.versions.toml").read_text())["versions"]
    major = str(versions["compileSdk"])
    minor = str(versions.get("compileSdkMinor", "0"))
    platform = f"{major}.{minor}" if int(major) >= 37 or minor != "0" else major
    criteria = (source / "gradle/gradle-daemon-jvm.properties").read_text()
    java = re.search(r"^toolchainVersion=(\d+)$", criteria, re.MULTILINE).group(1)
    return {"java": java, "platform": platform, "build_tools": f"{major}.0.0"}


def collect(root, source, upstream_sha):
    verify_player(source)
    actual_sha = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if actual_sha != upstream_sha:
        raise RuntimeError("构建源码与本次选定的上游提交不一致。")
    apk_dir = source / "AnkiDroid/build/outputs/apk/full/release"
    metadata = json.loads((apk_dir / "output-metadata.json").read_text())
    element = next(item for item in metadata["elements"] if {"filterType": "ABI", "value": "arm64-v8a"} in item["filters"])
    apk = apk_dir / element["outputFile"]
    tools = Path(os.environ["ANDROID_HOME"]) / "build-tools" / runtime(source)["build_tools"]
    certificate = subprocess.check_output([str(tools / "apksigner"), "verify", "--print-certs", str(apk)], text=True)
    if f"certificate SHA-256 digest: {CERTIFICATE}" not in certificate:
        raise RuntimeError("APK 签名与当前修改版不一致，停止发布。")
    destination = root / "dist"
    destination.mkdir(exist_ok=True)
    shutil.copy2(apk, destination / APK_NAME)
    shutil.copy2(root / "patches/no-audio-ducking.patch", destination / "no-audio-ducking.patch")
    with tarfile.open(destination / "AnkiDroid-no-audio-ducking-source.tar.gz", "w:gz") as archive:
        tracked = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).decode().split("\0")
        for name in filter(None, tracked):
            archive.add(source / name, arcname=f"AnkiDroid/{name}", recursive=False)
    version = re.sub(r"[^A-Za-z0-9_.-]", "-", element["versionName"])
    fingerprint = inputs_hash(root)
    tag = f"v{version}-noduck-{upstream_sha[:8]}-{os.environ['GITHUB_RUN_NUMBER']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    info = {
        "upstream_sha": upstream_sha,
        "inputs_hash": fingerprint,
        "patch_repository_sha": os.environ["GITHUB_SHA"],
        "version_name": element["versionName"],
        "version_code": element["versionCode"],
        "release_tag": tag,
        "certificate_sha256": CERTIFICATE,
        "apk_sha256": digest(apk),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (destination / "build-info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    notes = (
        f"AnkiDroid {element['versionName']}，播放卡片音频时保持后台音乐音量。\n\n"
        f"适用于 ARM64 手机，可覆盖安装此前的本仓库修改版。\n\n"
        f"上游源码：[ankidroid/Anki-Android@{upstream_sha[:8]}](https://github.com/ankidroid/Anki-Android/commit/{upstream_sha})。\n\n"
        "本次修改见附件补丁，完整对应源码、构建信息和 SHA-256 校验值一并提供。\n"
    )
    (destination / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    files = sorted(path for path in destination.iterdir() if path.name != "SHA256SUMS")
    (destination / "SHA256SUMS").write_text("".join(f"{digest(path)}  {path.name}\n" for path in files), encoding="utf-8")
    output(tag=tag, version=element["versionName"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("plan", "apply", "runtime", "collect", "record-check"))
    parser.add_argument("upstream_sha", nargs="?")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    source = ROOT / "upstream"
    if args.command == "plan":
        if not args.upstream_sha or not re.fullmatch(r"[0-9a-f]{40}", args.upstream_sha):
            parser.error("必须指定完整的上游提交 SHA")
        output(build=needs_build(ROOT, args.upstream_sha, args.force), upstream_sha=args.upstream_sha)
    elif args.command == "apply":
        apply_patch(ROOT, source)
    elif args.command == "runtime":
        output(**runtime(source))
    elif args.command == "record-check":
        output(recorded=record_check(ROOT))
    else:
        collect(ROOT, source, args.upstream_sha)


if __name__ == "__main__":
    main()
