#!/usr/bin/env python3
"""第2篇口播 · 背景动画构建器（Rio 直接跑，不用改代码）

背景 = 三层，本脚本负责前两层（第三层动效文字见规格表第 11 节）：
  第1层  AI 静图（智谱 CogView-4，1440x720/张，一张对应一句/一段文案）
  第2层  ★动画层★：每张静图拆成 2 个"机位"，用 ffmpeg zoompan 做缓慢运镜 + 硬切
         → 全片看起来是多机位剪出来的，不是静止图
  第3层  动效文字层（HTML/three.js 渲染成 PNG 序列，覆盖在动画层之上）

用法
  # ① 先裁掉智谱图右下角的「AI生成」水印（一次性，把原图目录变成可用图集）
  python3 mk_bg_kb2.py --crop-wm 原图目录 输出目录 [--wm-h 60]

  # ② 写 plan.json（段落 → 图 → 运镜），再出动画背景
  python3 mk_bg_kb2.py --plan plan_kb2.json --outdir bg_kb2

plan.json 格式（每段一条，时间单位秒，须覆盖全片时长）
  [{"start":0,"end":24.4,"images":["bgimg_kb2/b01_xx.jpg", ...],"move":"in"}, ...]
  move: in=推近(默认) out=拉远 panL=右向左移 panR=左向右移 up=下向上移

输出：<outdir>/bg.mp4  1280x720 / 30fps / h264 crf18 / +faststart（自带自查打印）
"""
import json, os, subprocess, sys, pathlib, shutil

W, H, FPS = 1280, 720, 30
Z_A, Z_B = 1.14, 1.30          # 机位A 推镜幅度 / 机位B 起始放大（=换个更近的角度）
MOVES = ['in', 'out', 'panL', 'panR', 'up']


# ────────────────────────── ① 水印裁剪 ──────────────────────────
def crop_wm(src_dir, dst_dir, wm_h=60):
    """智谱 CogView-4 的图右下角有白色大字「AI生成」水印。
    做法：裁掉底部 wm_h 像素，再拉回原尺寸（画面轻微下移，肉眼不可辨）。"""
    from PIL import Image
    src, dst = pathlib.Path(src_dir), pathlib.Path(dst_dir)
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(src.glob('*.jpg')) + sorted(src.glob('*.png')):
        out = dst / (p.stem + '.jpg')
        im = Image.open(p).convert('RGB')
        w, h = im.size
        im.crop((0, 0, w, h - wm_h)).resize((w, h), Image.LANCZOS).save(out, quality=95)
        n += 1
    print(f'  ✅ 水印已裁：{n} 张 → {dst}  (每张裁掉底部 {wm_h}px 后拉回 {w}x{h})')
    return dst


# ────────────────────────── ② 动画层 ──────────────────────────
def zoom_expr(move, nf, start=1.0, zmax=Z_A):
    mid_x, mid_y = 'iw/2-(iw/zoom/2)', 'ih/2-(ih/zoom/2)'
    if move == 'out':
        return f'max({zmax}-0.0010*on,{start})', mid_x, mid_y
    if move == 'panL':
        return f'{zmax}', f'(iw-iw/zoom)*(1-on/{nf})', mid_y
    if move == 'panR':
        return f'{zmax}', f'(iw-iw/zoom)*(on/{nf})', mid_y
    if move == 'up':
        return f'{zmax}', mid_x, f'(ih-ih/zoom)*(1-on/{nf})'
    return f'min({start}+0.0010*on,{zmax})', mid_x, mid_y       # in


def render_shot(src, out, dur, move, start=1.0):
    """静图 → 一段带运镜的视频。先放大到 2 倍再 zoompan，避免缩放糊。"""
    nf = max(2, int(dur * FPS))
    z, x, y = zoom_expr(move, nf, start)
    vf = (f'scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},'
          f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS},format=yuv420p")
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-framerate', str(FPS),
                        '-i', src, '-t', f'{dur:.3f}', '-vf', vf,
                        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', str(out)],
                       capture_output=True, text=True)
    if r.returncode:
        print(f'  ❌ {os.path.basename(src)}: {r.stderr[:160]}'); sys.exit(1)


def build(plan_path, outdir):
    plan = json.load(open(plan_path, encoding='utf-8'))
    outdir = pathlib.Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    for f in outdir.glob('s*.mp4'): f.unlink()
    parts, missing = [], []
    for si, seg in enumerate(plan):
        imgs = [p for p in seg['images'] if pathlib.Path(p).exists()]
        missing += [p for p in seg['images'] if not pathlib.Path(p).exists()]
        if not imgs: continue
        per = (seg['end'] - seg['start']) / len(imgs)
        for ii, src in enumerate(imgs):
            for tag, move, start in (('a', seg.get('move', 'in'), 1.0),          # 机位A 中景
                                     ('b', MOVES[(si + ii) % len(MOVES)], Z_B)):  # 机位B 换角度
                o = outdir / f's{si:02d}_{ii:02d}{tag}.mp4'
                render_shot(src, o, per / 2, move, start)
                parts.append(o)
        print(f'  段{si} {seg["start"]:.1f}-{seg["end"]:.1f}s  {len(imgs)}图 × 2机位 = {len(imgs)*2}镜头  '
              f'每镜头 {per/2:.1f}s  运镜={seg.get("move","in")}', flush=True)
    if missing:
        print(f'  ⚠️ 缺图 {len(missing)} 张：{missing[:5]}')
    lst = outdir / 'list.txt'
    lst.write_text('\n'.join(f"file '{p.resolve()}'" for p in parts) + '\n', encoding='utf-8')
    bg = outdir / 'bg.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst),
                    '-c', 'copy', '-movflags', '+faststart', str(bg)], check=True)
    check(bg, len(parts))
    return bg


def check(bg, nshot):
    info = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                           '-show_entries', 'stream=width,height,r_frame_rate,codec_name',
                           '-show_entries', 'format=duration,size', '-of', 'json', str(bg)],
                          capture_output=True, text=True).stdout
    d = json.loads(info); st = d['streams'][0]
    print(f'\n  ✅ {bg}')
    print(f'     {st["codec_name"]} {st["width"]}x{st["height"]} {st["r_frame_rate"]}  '
          f'{float(d["format"]["duration"]):.1f}s  {int(d["format"]["size"])/1e6:.1f}MB  {nshot} 个镜头')
    ok = (st['width'], st['height']) == (W, H) and st['r_frame_rate'] == '30/1'
    print('     自查：' + ('通过 ✔' if ok else '❌ 分辨率/帧率不对！'))
    # 抽帧（交付前务必人眼过一遍：有没有水印、有没有假字、拼接处有没有跳变）
    for i, t in enumerate([2, 30]):
        p = pathlib.Path(str(bg)).with_name(f'check_{t}s.jpg')
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(t), '-i', str(bg),
                        '-frames:v', '1', '-q:v', '3', str(p)], check=True)
    print(f'     已抽帧：check_2s.jpg / check_30s.jpg（超过时长的时间点会失败，属正常）')


if __name__ == '__main__':
    a = sys.argv
    if '--crop-wm' in a:
        i = a.index('--crop-wm')
        crop_wm(a[i+1], a[i+2], int(a[a.index('--wm-h')+1]) if '--wm-h' in a else 60)
    elif '--plan' in a:
        build(a[a.index('--plan')+1], a[a.index('--outdir')+1] if '--outdir' in a else 'bg_kb2')
    else:
        print(__doc__)
