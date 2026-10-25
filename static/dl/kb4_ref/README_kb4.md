# kb4 样片施工图（Hermes → Rio）

## 这是什么
第 4 篇开头 10.5 秒样片，**用户已看过这个水准**。用户指令：「你让 RIO 做吧」
→ 由你按这个路子把**第 3、4 篇整篇**做成片（**画面层**）；**用户自己配音**是主声，AI 声只是占位。

## 文件清单
- `kb4_sample_v2.mp4` —— 成品样片（1280×720 / 30fps / 10.5s / AAC 48k? 实际 24k mono）
- `spec_kb4.json` —— 用的 spec（grammar=t2_keynote_ui, 1280×720, fps 30, duration 10.5）
- `sub2.ass` —— 底部字幕（白字 44px / MarginV=46 / 字体 WenQuanYi Zen Hei）

## 命令（我这边实测可用的原样）
```bash
# 1 渲画面（--spec 走 clip.html）
uv run --with playwright python scripts/engine/render.py \
   --spec spec_kb4.json --out kb4_open.mp4 --fps 30
# 2 验 spec 合法性（快，先跑这个）
uv run --with playwright python scripts/engine/render.py --spec spec_kb4.json --stills 1.0,5.0 --out ./out
# 3 版面审计（出界/字太小/压字）——红灯不出片
uv run --with playwright python scripts/engine/render.py --spec spec_kb4.json --audit audit.json
# 4 贴音轨 + 烧字幕（一次编码）
ffmpeg -y -i kb4_open.mp4 -i voice.m4a -vf "ass=sub2.ass" -map 0:v -map 1:a \
   -c:v libx264 -crf 19 -preset medium -pix_fmt yuv420p -c:a aac -b:a 128k -shortest out.mp4
```

## 我踩过的三个坑（照抄别再踩）
1 **spec 格式**：顶层必须是 `{grammar, duration, fps, width, height, theme, cues}`；缺 `grammar` 它**直接拒绝渲染**（"spec 缺 grammar"）✗。
   cue 形如 `{"at": 秒, "kind": "line"|"point", "text": "…"}`。
2 **中文字体（最容易翻车）** ✗：系统里**没有 Noto Sans CJK** ✗，字幕写 Noto 名会出**豆腐块** ✗。
   → 用**系统确实存在的**：`WenQuanYi Zen Hei`（文泉驿正黑）✓。先用 `fc-list :lang=zh` 确认。
3 **别用 `nohup` 起渲染**（我这边的执行器会拦截）；分片长任务要可续跑。

## 验收（必须全过才交我 ✗）
- 尺寸 **1280×720**、**30fps**；每段 2–6 秒的镜头表（**口播长段可放宽** ✓ 它自己也允许）
- `--audit` **红灯 0**；**黄灯也报出来**
- 音轨非静音：`ffmpeg -i out.mp4 -af volumedetect -f null -` → mean_volume 应在 −30…−15 dB 区间
- **字幕必须是真字**（不能豆腐块）：抽 3 帧看字幕带，连通块数 >15 且宽度标准差 >3（我会用同一套脚本复核）
- 台词**逐字取自用户定稿** ✗ 不许改字、不许自编、不许加旁白
- **AI 声只作占位** ✗ 不作为交付声；用户的声音到位后只换音轨、画面不动

## 顺序与交付
1 先做**第 4 篇**（654 字，约 2 分钟）→ 交我审 → 我交用户
2 再做**第 3 篇**（1329 字，约 4 分钟）
3 一律：上传口 + sha256 + CHANGE_NOTE；我审后交用户；**一次一个，不并行上线**
