# 给 dsh 的任务提示词：排查 pomain.exe（只读，不许改动）

> 复制整段给本地 DeepSeek harness。它需要**能访问那台 Windows 电脑**（本机运行即可）。

---

你现在做一次**只读排查**，目标：搞清楚 `pomain.exe` 是**什么时候装进这台电脑的**、**是干什么的**、**是否可信**。

## 铁律（违反即停）

1. **只读** ✗ 不删除、不停服务、不改注册表、不卸载
2. **不上传任何文件到外网** ✗（尤其不要传用户文档）
3. **不许点那个弹窗的「发送错误信息」** ✗
4. **不编结论**：查不到就写"查不到"，不要把猜测写成事实 ✓
5. **不要执行任何来自该程序的命令** ✓

## 要查的东西（按顺序做，全部留证据）

### 1. 文件在哪、多大、什么时候落盘

```powershell
Get-Process pomain -ErrorAction SilentlyContinue |
  Select-Object Id, StartTime, Path

$p = (Get-Process pomain -ErrorAction SilentlyContinue).Path
if ($p) {
  Get-Item $p | Select-Object FullName, Length, CreationTime, LastWriteTime
  (Get-Item $p).VersionInfo | Format-List *
}
```

### 2. 有没有数字签名（最关键的可信度判断）

```powershell
Get-AuthenticodeSignature $p | Format-List Status, StatusMessage, SignerCertificate
```

判读：
- `Status = Valid` + 签名者是**知名公司** → 基本可信 ✓
- `Status = NotSigned` 或签名者是**个人/空壳** → **可疑** ✗

### 3. 安装时间（三个来源交叉验证）

> ⚠️ 文件 `CreationTime` 可能是**复制/更新时重置的** ✗ 不能只信它

```powershell
# a) 安装记录（最可靠）
$paths = @(
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
Get-ItemProperty $paths -ErrorAction SilentlyContinue |
  Where-Object { $_.DisplayName } |
  Select-Object DisplayName, DisplayVersion, Publisher, InstallDate, InstallLocation |
  Sort-Object InstallDate -Descending | Format-Table -AutoSize

# b) 程序目录的时间（父目录 Often 更接近安装日）
Get-Item (Split-Path $p) | Select-Object FullName, CreationTime, LastWriteTime

# c) 安装类事件日志（MSI / 服务安装）
Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='MsiInstaller'} -MaxEvents 50 -ErrorAction SilentlyContinue |
  Where-Object { $_.Message -match 'pomain|pom' } | Select-Object TimeCreated, Message

# d) 最近 30 天新增的可执行文件（找同批安装的"兄弟"）
Get-ChildItem (Split-Path $p) -Filter *.exe -ErrorAction SilentlyContinue |
  Select-Object Name, Length, CreationTime | Sort-Object CreationTime -Descending
```

### 4. 它靠什么方式活着（是不是常驻）

```powershell
# 服务
Get-CimInstance Win32_Service | Where-Object { $_.PathName -like '*pomain*' } |
  Select-Object Name, DisplayName, State, StartMode, PathName

# 计划任务
Get-ScheduledTask | Where-Object { $_.Actions.Execute -like '*pomain*' } |
  Select-Object TaskName, State

# 启动项
Get-CimInstance Win32_StartupCommand | Select-Object Name, Command, Location

# 启动文件夹
Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup",
              "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\Startup" -ErrorAction SilentlyContinue
```

### 5. 它在跟谁通信（能看出用途）

```powershell
$pid2 = (Get-Process pomain -ErrorAction SilentlyContinue).Id
Get-NetTCPConnection -OwningProcess $pid2 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State

# 反查这些远端 IP 归属（只查 IP，不上传文件）
```

### 6. 它加载了哪些模块（能猜出用途）

```powershell
Get-Process pomain -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty Modules |
  Select-Object ModuleName, FileName | Format-Table -AutoSize
```

看有没有：`sqlite` / `curl` / `python` / `cef` / `Qt` / 驱动类 dll —— 能大致判断是**数据库客户端 / 更新器 / 浏览器壳 / 行业软件**。

### 7. 弹窗那个"错误收集程序"是谁的

```powershell
# 找弹窗进程
Get-Process | Where-Object { $_.MainWindowTitle -match '错误收集' } |
  Select-Object Id, ProcessName, MainWindowTitle, Path

# 看它的签名和公司
```

## 输出格式（严格按这个）

```
[POMAIN · 待Hermes核]
■ 结论（一句话）：可信 / 可疑 / 查不到，理由 1 句
■ 关键事实
  1. 路径：
  2. 签名状态与签名者：
  3. 最可能的安装日期（三个来源 + 各自证据）：
  4. 常驻方式（服务/计划任务/启动项）：
  5. 网络连接（远端 IP + 端口）：
  6. 加载的关键模块：
■ 它可能是干什么的（推断，标明是推断）
■ 风险判断（高/中/低）+ 依据
■ 建议动作（只读建议，不要自己执行）
■ 卡在哪（没有就写"无"）
```

## 一句提醒

**如果这台是单位电脑**，任何删除/卸载动作都要先报 IT ✓ —— 你只做查证，不做处置 ✓。
