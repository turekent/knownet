#!/usr/bin/env python3
"""圆窗外泄漏检测（rb2 版）——判"人物/衣服有没有伸出圆框外"

为什么换这一个口径：
  旧口径「成片 − （背景+圆窗无人物合成）」依赖"底板"怎么搭（圆遮罩糊几像素、
  贴片怎么重采样），同一份片子不同人搭底板能量出 165 和 751 两个数，不可复现。
  新口径不用底板，直接跟【纯背景帧】比，方法无关：
      圆外环带 d ∈ (r+3, r+25) 内，|成片 − 纯背景| > 14 的像素数  → 应≈0
  物理含义：圆外这一圈只该是背景。出现差异=有东西（人物/衣服/白边）漏出去了。

用法：
  python3 ring_leak.py --frame 成片.mp4 --bg 背景.mp4 [--t 2] [--r 150] [--cx 1090] [--cy 570]
  多帧一次量：--t 1,2,5,7
"""
import argparse, subprocess, sys, json
import numpy as np
from PIL import Image

W, H = 1280, 720


def gray_rgb(video, t):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', video, '-frames:v', '1',
                          '-vf', f'scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True).stdout
    if len(raw) != W * H * 3:
        return None
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.int16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frame', required=True, help='待测成片')
    ap.add_argument('--bg', required=True, help='同一时刻的纯背景（或用成片的背景源）')
    ap.add_argument('--t', default='2', help='取样时刻，逗号分隔')
    ap.add_argument('--r', type=int, default=150)
    ap.add_argument('--cx', type=int, default=1090)
    ap.add_argument('--cy', type=int, default=570)
    ap.add_argument('--thr', type=int, default=14, help='像素差阈值')
    ap.add_argument('--inner', type=int, default=3, help='环带内边界 = r+inner（避开抗锯齿）')
    ap.add_argument('--outer', type=int, default=25, help='环带外边界 = r+outer')
    ap.add_argument('--keep-y', type=int, default=548, dest='keep_y',
                    help='只测该行以下（=人物遮罩分界；这行以上头部是要露在圆外的，不算泄漏）')
    a = ap.parse_args()

    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt((xx - a.cx) ** 2 + (yy - a.cy) ** 2)
    ring = (d > a.r + a.inner) & (d <= a.r + a.outer) & (yy >= a.keep_y)
    total = int(ring.sum())
    bad_all, rows = 0, []
    for t in [x.strip() for x in a.t.split(',') if x.strip()]:
        f, b = gray_rgb(a.frame, t), gray_rgb(a.bg, t)
        if f is None or b is None:
            print(f'  t={t}: ⚠️ 取帧失败'); continue
        diff = np.abs(f - b).max(2)
        bad = int(((diff > a.thr) & ring).sum())
        bad_all += bad
        worst = float(diff[ring].max())
        rows.append((t, bad, worst))
        print(f'  t={t:>5}s  环带泄漏像素 {bad:5d} / {total}   (该环带最大像素差 {worst:.0f})')

    if not rows:
        sys.exit('没能取到帧')
    worst_leak = max(r[1] for r in rows)
    worst_diff = max(r[2] for r in rows)
    verdict = 'PASS' if (worst_leak <= 50 and worst_diff <= 30) else 'FAIL'
    print(f'\n判定：{verdict}   （判据：每帧环带泄漏像素 ≤50 且该环带最大像素差 ≤30）')
    print('      基线（Hermes 参考片 kb2_ref10.mp4，4 帧）：泄漏 0/5/22/8，最大差 14~21')
    print('      参考：把 --inner 改成 1 会量到 ~490 像素——那是 r+1~r+3 的抗锯齿，不是泄漏，不要拿它判定')
    print(json.dumps({'ring_px': total, 'worst_leak': worst_leak, 'worst_diff': worst_diff,
                      'per_frame': [{'t': r[0], 'leak': r[1], 'maxdiff': r[2]} for r in rows],
                      'verdict': verdict}, ensure_ascii=False))
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
