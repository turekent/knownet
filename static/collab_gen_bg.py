#!/usr/bin/env python3
"""智谱 CogView-4 出背景图。用法: python3 gen_bg.py "提示词" 输出路径 [尺寸]
尺寸默认 1440x810（16:9，配合 1280x720 推镜有余量）"""
import json, sys, time, pathlib, urllib.request

KEY = pathlib.Path('/home/ubuntu/.zhipu_key').read_text().strip()
URL = 'https://open.bigmodel.cn/api/paas/v4/images/generations'

def gen(prompt, out, size='1440x720', model='cogview-4-250304', retries=3):
    body = json.dumps({'model': model, 'prompt': prompt, 'size': size}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            u = d['data'][0]['url']
            img = urllib.request.urlopen(u, timeout=180).read()
            pathlib.Path(out).write_bytes(img)
            return len(img)
        except Exception as e:
            print(f'    重试 {i+1}/{retries}: {str(e)[:120]}')
            time.sleep(5)
    raise RuntimeError(f'失败: {prompt[:40]}')

if __name__ == '__main__':
    prompt, out = sys.argv[1], sys.argv[2]
    size = sys.argv[3] if len(sys.argv) > 3 else '1440x720'
    t0 = time.time()
    n = gen(prompt, out, size)
    print(f'  ✅ {out}  {n/1024:.0f} KB  {time.time()-t0:.0f}s')
