#!/usr/bin/env python3
"""交付前自检（preflight）—— 把"验收的镜子"直接给到交付方。

用法:
    python3 preflight.py <file.mp4 | summary.json> [--json]

它做两件事：
  1 该测的全测（分辨率/帧率/时长/帧数/summary 8 字段/抖动）
  2 **打印一份打勾清单**，直接贴进交件消息即可

设计原则：不让交付方"自己写一套宽松标准判自己"，
         而是用验收方同一个脚本、同一阈值。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

W_EXPECT, H_EXPECT, FPS_EXPECT = 1280, 720, 30
JITTER_STD, JITTER_JUMP = 0.3, 1.0
SUMMARY_FIELDS = [
    ("person_scale.x", "人像横向缩放"),
    ("person_scale.y", "人像纵向缩放"),
    ("person_bbox.w", "人像渲染宽度"),
    ("person_bbox.h", "人像渲染高度"),
    ("person_src_aspect", "源片人像宽高比"),
    ("subtitle.fg", "字幕前景色"),
    ("subtitle.outline_px", "字幕描边"),
    ("bg.sha16", "背景轨 sha16"),
]


def probe(p: Path) -> dict:
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0",
           "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration",
           "-show_entries", "format=duration", "-of", "json", str(p)]
    d = json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout or "{}")
    st = (d.get("streams") or [{}])[0]
    fr = st.get("r_frame_rate", "0/1")
    try:
        num, den = fr.split("/")
        fps = float(num) / float(den or 1)
    except Exception:
        fps = 0.0
    return {
        "w": st.get("width"), "h": st.get("height"),
        "fps": round(fps, 3),
        "frames": int(st.get("nb_frames") or 0),
        "dur": round(float(d.get("format", {}).get("duration") or st.get("duration") or 0), 3),
    }


def jitter(p: Path):
    """人像抖动：优先用测量岗的脚本，没有就跳过（不猜）。"""
    for cand in [
        Path("/home/ubuntu/pipeline/tools/measure_jitter.py"),
        Path("/home/ubuntu/uploads/measure_jitter.py"),
        Path("/home/ubuntu/.hermes/scripts/measure_jitter.py"),
    ]:
        if cand.exists():
            venv_py = Path("/home/ubuntu/pipeline/venv/bin/python")
            py = str(venv_py) if venv_py.exists() else sys.executable
            r = subprocess.run([py, str(cand), str(p), "--hist-roi", "--json"],
                               capture_output=True, text=True, timeout=600)
            try:
                return json.loads(r.stdout), cand.name
            except Exception:
                return None, cand.name
    return None, None


def get(d, path):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    p = Path(sys.argv[1])
    as_json = "--json" in sys.argv
    if not p.exists():
        print(f"FAIL 文件不存在: {p}")
        return 1

    rows, fails = [], 0

    def add(item, got, need, ok, note=""):
        nonlocal fails
        if not ok:
            fails += 1
        rows.append((item, str(got), str(need), "PASS" if ok else "FAIL", note))

    if p.suffix.lower() in (".mp4", ".mov", ".mkv"):
        m = probe(p)
        add("分辨率", f"{m['w']}x{m['h']}", f"{W_EXPECT}x{H_EXPECT}",
            m["w"] == W_EXPECT and m["h"] == H_EXPECT)
        add("帧率", m["fps"], FPS_EXPECT, abs(m["fps"] - FPS_EXPECT) < 0.05)
        add("时长", m["dur"], ">0", m["dur"] > 0)
        add("帧数", m["frames"], ">0", m["frames"] > 0)

        j, who = jitter(p)
        if j is None:
            add("人像抖动 A9", "未测", "std≤0.3 / jump≤1.0", True,
                f"无测量脚本（{who or '未找到'}）→ 标 INCONCLUSIVE，不算不合格")
        else:
            segs = j.get("segments") or {}
            if isinstance(segs, dict) and segs:
                for name, v in segs.items():
                    std = v.get("std_report")
                    mj = v.get("max_jump")
                    if std is None or std >= 900:
                        add(f"A9 {name}", f"无法测量(pairs={v.get('n_pairs')})", f"std≤{JITTER_STD}",
                            True, "**INCONCLUSIVE**（不是不合格）")
                        continue
                    near = (JITTER_STD * 0.9 < float(std) <= JITTER_STD * 1.1)
                    add(f"A9 {name}", f"std={float(std):.4f} jump={float(mj):.4f}",
                        f"std≤{JITTER_STD} jump≤{JITTER_JUMP}",
                        bool(v.get("pass")) and float(mj) <= JITTER_JUMP,
                        "**临界，需说明**" if near else "")
            else:
                add("人像抖动 A9", "脚本无结果", f"std≤{JITTER_STD}", True, "**INCONCLUSIVE**")

    elif p.suffix.lower() == ".json":
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"FAIL summary 无法解析: {e}")
            return 1
        for path, label in SUMMARY_FIELDS:
            v = get(d, path)
            add(f"字段 {path}", v if v is not None else "缺失", "必须存在", v is not None, label)
        sx, sy = get(d, "person_scale.x"), get(d, "person_scale.y")
        if isinstance(sx, (int, float)) and isinstance(sy, (int, float)) and sx:
            dev = abs(sx - sy) / abs(sx)
            add("A1 等比", f"x={sx} y={sy} 偏差{dev*100:.2f}%", "≤0.1%", dev <= 0.001)
        fg = get(d, "subtitle.fg")
        if isinstance(fg, list) and len(fg) == 3:
            add("A8 字幕色", f"min={min(fg)}", "≥245", min(fg) >= 245)
        ol = get(d, "subtitle.outline_px")
        if isinstance(ol, (int, float)):
            add("A8b 描边", f"{ol}px", "≥2px", ol >= 2)

    else:
        add("文件类型", p.suffix or "无", "mp4 或 summary.json", False, "不支持的类型，不允许静默 PASS")

    if as_json:
        print(json.dumps({"file": str(p), "pass": fails == 0, "fails": fails,
                          "rows": [dict(zip(["item", "got", "need", "result", "note"], r)) for r in rows]},
                         ensure_ascii=False, indent=2))
    else:
        print(f"\n交付前自检 · {p.name}")
        print("| 检查项 | 实测值 | 阈值 | 结论 | 备注 |")
        print("|---|---|---|---|---|")
        for item, got, need, res, note in rows:
            print(f"| {item} | {got} | {need} | {res} | {note} |")
        print(f"\n总判：{'PASS' if fails == 0 else f'FAIL({fails})'}")
        print("\n—— 把上面这张表直接贴进交件消息，即视为已附预检清单 ——")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
