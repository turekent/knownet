# 给 dsh 的任务：跑通抖音创作者中心的每日采集（只读、只自己账号）

> 目标不是"重写一遍"，而是**把选择器校准到真实页面**，然后**稳定每天跑一次**。
> 代码已经写好并跑通过 CSV 那半段；**采集器那半段的选择器是猜的，必须由你在真实页面上校准。**

---

## 一、在哪跑

**在用户这台 Windows 上跑** ✓（不是服务器）

原因：采集需要**用户自己的抖音登录态**，登录态不能离开他的机器 ✗

---

## 二、拿代码

```
https://knownet.digitalmind.chat/static/dl/kb_workbench_v1.tar.gz
```

3 个脚本 + README + 样例。解压到任意目录。

---

## 三、装环境

```powershell
python -m pip install playwright
python -m playwright install chromium
```

验证：
```powershell
python -c "from playwright.sync_api import sync_playwright; print('ok')"
```

---

## 四、第一次登录（需要用户配合）

```powershell
python collect.py --login
```

会弹出一个**有界面的浏览器** ✓ 让用户**自己扫码登录** ✓ 你**不要代填任何账号密码** ✗
登录成功后脚本会把登录态存到 `collector/state.json` ✓

---

## 五、你的核心任务：校准选择器（这一步只有你能做）

打开创作者中心的作品管理页：
```
https://creator.douyin.com/creator-micro/content/manage
```

**要做的**：
1. 用 `--headed` 跑一次：
   ```powershell
   python collect.py --collect --headed
   ```
2. 看 `collector/last_page.png` —— 它到底抓到了什么？
3. 打开浏览器的开发者工具（或 `page.evaluate`），**读出真实的表格结构**：
   - 作品列表是 `<table>` 还是 `<div>` 卡片？
   - 每一行的 class 是什么？
   - 标题、播放量、完播率分别在哪个子节点？
4. **改写 `collect.py` 里 `do_collect()` 的 `rows = pg.evaluate(...)` 那段**，换成真实选择器
5. 重跑，直到**抓到的字段 = 页面上肉眼能看到的字段**

**校准标准**（必须逐条对上）：
| 页面上有 | 抓到了吗 |
|---|---|
| 作品标题 | |
| 发布时间 | |
| 播放量 | |
| 完播率 | |
| 点赞 / 评论 / 分享 | |
| 涨粉 | |

**抓不到的字段，如实写"抓不到"** ✗ 不要瞎猜数字 ✗

---

## 六、跑一次真实的，然后交给我

```powershell
python collect.py --collect
```

**交付 4 样**：
1. **改好的 `collect.py`**（附 diff 或说明改了哪几行）
2. **`collector/last_page.png`**（证明它真的打开了页面）
3. **一份抓取样本** —— ⚠️ **脱敏**：只保留**字段名 + 数值**，标题可保留前 8 个字，**不要带账号 ID / 手机号 / 粉丝昵称** ✗
4. **一句话说明**：哪些字段抓不到、为什么

---

## 七、稳定每天跑一次

用 **Windows 任务计划程序**：
- 触发器：**每天 08:30**
- 操作：`python C:\...\kb_workbench\collect.py --collect`
- **勾选"只在用户登录时运行"** ✓（登录态需要用户会话）
- **失败重试 1 次**，间隔 15 分钟

**跑完把 `collector/collected.json` 留着** ✓ 不要自动上传 ✗

---

## 八、红线（违反即停）

1. **只抓用户自己的账号** ✓ 代码里不许出现"按关键词搜别人"的分支 ✗
2. **一天最多 1 次** ✓（脚本里有 1 小时锁，你也不要绕过）
3. **不并发、不批量、不改 UA、不用代理** ✗
4. **数据不出本机** ✗ 不上传任何云端
5. **不代填账号密码** ✗ 登录必须用户自己扫码
6. **抓不到就说抓不到** ✗ 不许编数字

---

## 九、交付格式

```
[COLLECT · 待Hermes核]
■ 结论：跑通 / 部分跑通 / 没跑通
■ 改了哪里（collect.py 第几行 → 改成什么）
■ 抓到的字段（逐条打勾）
■ 抓不到的字段 + 原因
■ last_page.png 路径
■ 样本（脱敏）前 2 条
■ 任务计划是否已建
■ 卡在哪
```
