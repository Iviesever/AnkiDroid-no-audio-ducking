# AnkiDroid 播放音频时保持后台音乐音量

这个补丁让 AnkiDroid 播放卡片音频时，不再压低后台音乐音量。单词发音和音乐可以同时播放。

改动集中在 `SoundTagPlayer.kt`：移除音频焦点申请及对应的释放代码，保留原有的播放、停止和错误处理。没有新增设置项。

## 下载与安装

[下载最新 APK](https://github.com/Iviesever/AnkiDroid-no-audio-ducking/releases/latest/download/AnkiDroid-no-audio-ducking-arm64-v8a.apk) · [查看全部版本](https://github.com/Iviesever/AnkiDroid-no-audio-ducking/releases)

安装包适用于 ARM64 手机，包名沿用 `com.ichi2.anki`。本仓库后续构建使用同一签名，可以覆盖安装本修改版。官方版签名不同，首次换用时需要先备份牌组和媒体，再卸载官方版。

## 自动更新

每天北京时间 10:17 检查 [AnkiDroid 上游 main](https://github.com/ankidroid/Anki-Android)。有更新就拉取对应提交、应用补丁、编译并发布 APK。补丁或构建流程改动后也会重新编译。

补丁无法应用、编译失败或签名不匹配时，流程停止，上一份可用 APK 保持不变。失败原因可以在 [Actions](https://github.com/Iviesever/AnkiDroid-no-audio-ducking/actions) 中查看。也可以打开“跟进上游并构建 APK”，点击“Run workflow”手动运行。

每个发布版本都附有完整源码、补丁、构建信息和文件校验值。`last-build.json` 记录最近一次成功构建的上游提交。跟随 `main` 构建，版本号与上游一致。

没有上游更新时跳过编译，每 28 天记录一次检查时间，保持定时任务启用。

## 补丁与源码

[查看补丁](patches/no-audio-ducking.patch)。本仓库及对应源码按 [GPL-3.0-or-later](COPYING) 分发。
