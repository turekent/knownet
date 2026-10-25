#!/usr/bin/env python3
"""A7 接缝检查（v2.2：去偏后结构性差异判定）+ 同帧硬切反例生成。

v2.2 判据（实测于 2026-10-24，见 reports/A7_接缝测法_否决与替代_20261024.md）：
  d = gray(A_last) - gray(B_first); bias = mean(d); r = d - bias
  f5 = fraction(|r| > 5)
    f5 < 0.05%            → 同帧硬切 FAIL
    0.05% <= f5 < 0.20%   → INCONCLUSIVE（报 f5/p99/bias，人工看一眼）
    f5 >= 0.20%           → PASS（辅证 p99 >= 4 加严信心）
废弃旧口径「mean|Δ| < 0.5 判同帧」：二次编码整体电平偏移可达 1.48 灰阶，
会让真接缝 pair3/4（0.378/0.241）误判 FAIL、同帧反例（1.485）误判 PASS。
"""
import argparse, json, os
import cv2
import numpy as np

F5_FAIL = 0.05    # %
F5_PASS = 0.20    # %
STRUCT_DIFF = 5.0 # 灰度级
THR_STD_DELTA = 3.0
THR_SKIN_DELTA = 0.005


def frames(path):
    cap = cv2.VideoCapture(path)
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    cap.release()
    if not out:
        raise RuntimeError(f"decode failed: {path}")
    return out


def gray(f):
    return cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)


def skin_ratio(frame):
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    cr, cb = ycrcb[..., 1], ycrcb[..., 2]
    return float(((cr > 133) & (cr < 173) & (cb > 77) & (cb < 127)).mean())


def seam_metrics(fa, fb):
    ga, gb = gray(fa), gray(fb)
    d = ga - gb
    bias = float(d.mean())
    r = d - bias
    f5 = float((np.abs(r) > STRUCT_DIFF).mean() * 100.0)
    p99 = float(np.percentile(np.abs(r), 99))
    if f5 < F5_FAIL:
        verdict = "FAIL"
    elif f5 < F5_PASS:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"
    std_a, std_b = float(ga.std()), float(gb.std())
    sk_a, sk_b = skin_ratio(fa), skin_ratio(fb)
    flags = []
    if abs(std_a - std_b) > THR_STD_DELTA:
        flags.append(f"std差{abs(std_a - std_b):.2f}>3")
    if abs(sk_a - sk_b) > THR_SKIN_DELTA:
        flags.append(f"肤色占比差{abs(sk_a - sk_b) * 100:.2f}%>0.5%")
    return {
        "raw_mean_abs_diff": round(float(np.abs(d).mean()), 4),
        "bias": round(bias, 4),
        "resid_mean_abs_diff": round(float(np.abs(r).mean()), 4),
        "f5_pct": round(f5, 4),
        "p99_resid": round(p99, 2),
        "thresholds": {"f5_fail": F5_FAIL, "f5_pass": F5_PASS, "struct_diff": STRUCT_DIFF},
        "verdict": verdict,
        "std_a": round(std_a, 3), "std_b": round(std_b, 3),
        "skin_a": round(sk_a, 5), "skin_b": round(sk_b, 5),
        "manual_flags": flags,
    }


def make_sameframe_counterexample(seg_a, seg_b, out_path, crf=8):
    """把 seg_b 的首帧替换成 seg_a 的末帧，用 x264 重编码 → 接缝必为同一帧。"""
    import subprocess, tempfile, shutil
    A = frames(seg_a)
    B = frames(seg_b)
    seq = [A[-1]] + B[1:]
    tmp = tempfile.mkdtemp(prefix="ce_", dir=os.path.dirname(out_path) or None)
    try:
        for i, f in enumerate(seq, 1):
            cv2.imwrite(os.path.join(tmp, f"{i:04d}.png"), f)
        subprocess.run(["ffmpeg", "-v", "error", "-framerate", "30",
                        "-i", os.path.join(tmp, "%04d.png"),
                        "-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
                        "-y", out_path], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return len(seq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="*", help="A.mp4 B.mp4 C.mp4 … 按顺序给相邻段")
    ap.add_argument("--make-counter", nargs=3, metavar=("SEG_A", "SEG_B", "OUT"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    out = {"pairs": []}

    if args.make_counter:
        a, b, o = args.make_counter
        n = make_sameframe_counterexample(a, b, o)
        out["counterexample"] = {"out": o, "frames": n, "bytes": os.path.getsize(o)}

    if args.pairs:
        for i in range(len(args.pairs) - 1):
            A, B = frames(args.pairs[i]), frames(args.pairs[i + 1])
            m = seam_metrics(A[-1], B[0])
            m["pair"] = f"{os.path.basename(args.pairs[i])} | {os.path.basename(args.pairs[i+1])}"
            out["pairs"].append(m)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        for p in out["pairs"]:
            flag = ("；".join(p["manual_flags"])) or "无"
            print(f"{p['pair']}\n  f5={p['f5_pct']:.2f}%（阈<{F5_FAIL}FAIL/≥{F5_PASS}PASS）→ {p['verdict']}"
                  f" | 去偏残差{p['resid_mean_abs_diff']} p99={p['p99_resid']} bias={p['bias']:+.3f}"
                  f" | raw {p['raw_mean_abs_diff']} | 辅证:{flag}")
        if "counterexample" in out:
            c = out["counterexample"]
            print(f"反例 {c['out']} {c['frames']}帧 {c['bytes']}B")


if __name__ == "__main__":
    main()
