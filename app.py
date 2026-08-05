#!/usr/bin/env python3
"""人脉知识图谱 v2.0 — 多用户 + 管理后台"""
import os, json, uuid, base64, datetime, sqlite3, re, urllib.request, hashlib, secrets, time
from functools import wraps
from flask import Flask, request, jsonify, render_template, g, session, redirect, url_for

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
MAIN_DB = os.path.join(APP_ROOT, "knownet.db")
USERDATA_DIR = os.path.join(APP_ROOT, "userdata")
SCHEMA_PATH = os.path.join(APP_ROOT, "schema.sql")
# 上传目录移出 static/（避免公网裸访问），改走鉴权接口
UPLOAD_DIR = os.path.join(APP_ROOT, "data", "uploads")

app = Flask(__name__, template_folder="templates", static_folder="static")
# secret_key：环境变量优先，其次持久化密钥文件（重启不失效、多进程一致）
app.secret_key = os.environ.get("KNOWNET_SECRET_KEY", "")
if not app.secret_key:
    _key_file = os.path.join(APP_ROOT, "knownet_secret.key")
    if os.path.exists(_key_file):
        with open(_key_file) as f:
            app.secret_key = f.read().strip()
    else:
        app.secret_key = secrets.token_hex(32)
        with open(_key_file, "w") as f:
            f.write(app.secret_key)
        os.chmod(_key_file, 0o600)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
# HTTPS 部署：cookie 加 Secure + SameSite 防 CSRF/中间人
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(USERDATA_DIR, exist_ok=True)

# API Keys
DS_KEY_PATH = os.environ.get("DS_KEY_PATH", os.path.expanduser("~/.ds_key"))
ZHIPU_KEY = os.environ.get("ZHIPU_KEY", "")

# Auth - default admin password from env, fallback: 持久化到文件避免锁死
KNOWNET_ADMIN_PASSWORD = os.environ.get("KNOWNET_ADMIN_PASSWORD", "")
if not KNOWNET_ADMIN_PASSWORD:
    _pw_file = os.path.join(APP_ROOT, "knownet_admin_password.txt")
    if os.path.exists(_pw_file):
        with open(_pw_file) as f:
            KNOWNET_ADMIN_PASSWORD = f.read().strip()
    else:
        KNOWNET_ADMIN_PASSWORD = secrets.token_urlsafe(10)
        with open(_pw_file, "w") as f:
            f.write(KNOWNET_ADMIN_PASSWORD)
        os.chmod(_pw_file, 0o600)

# ==================== i18n ====================

LANG = {
    "zh": {
        "app_title": "人脉图谱",
        "page_title": "人脉 · 知识图谱",
        "count": "{} 人",
        "search_placeholder": "搜名字、标签、学校...",
        "add_btn": "+ 加人",
        "tab_all": "全部",
        "tab_path": "找路径",
        "tab_tags": "标签",
        "empty_title": "还没添加联系人",
        "empty_hint": "点击右上角「+ 加人」\n拍照或粘贴微信截图即可",
        "modal_add": "添加联系人",
        "upload_hint": "点击上传微信截图/名片照片\n或在下方直接粘贴文字",
        "paste_hint": "或直接粘贴备注文字...\n例如：张三，江西南昌人，暨大2010届，做建材，喜欢钓鱼，两个娃",
        "ai_btn": "🤖 AI 解析并添加",
        "search_network": "🔗 查找两人之间的最短路径",
        "select_a": "选择第一个人...",
        "select_b": "选择第二个人...",
        "find_btn": "🔍 查找路径",
        "no_path": "未找到路径",
        "found_depth": "找到 {} 度关系",
        "same_person": "同一个人",
        "no_detail": "暂无详细信息",
        "interests_label": "兴趣",
        "relations_label": "关联人物",
        "raw_notes_label": "原始备注",
        "login_title": "人脉知识图谱 · 多用户版",
        "login_username": "用户名",
        "login_password": "密码",
        "login_btn": "进入",
        "login_register_hint": "首次使用？",
        "login_register_link": "立即注册 →",
        "register_title": "申请使用 KnowNet",
        "register_username": "用户名（中英文均可）",
        "register_password": "密码（6-16位，含字母数字）",
        "register_password2": "确认密码",
        "register_btn": "提交申请",
        "register_login_hint": "已有账号？",
        "apply_hook": "KnowNet 目前是小范围试用。告诉我你是谁、为什么需要它——认真写的申请我都会看。",
        "apply_reason": "为什么需要它？（至少10个字）",
        "apply_source": "从哪看到的？（选填：公众号/朋友/其他）",
        "apply_after": "审核通过后即可登录，通常1天内。",
        "register_login_link": "立即登录",
        "admin_title": "管理后台",
        "admin_back": "← 返回",
        "admin_logout": "退出",
        "admin_users": "👥 用户列表",
        "admin_applications": "📋 待审核申请",
        "admin_appl_pending": "待审核",
        "admin_appl_approve": "通过",
        "admin_appl_reject": "拒绝",
        "admin_appl_empty": "暂无待审核申请",
        "admin_create": "+ 创建用户",
        "admin_create_title": "创建新用户",
        "admin_create_user": "用户名（登录用）",
        "admin_create_pwd": "初始密码（用户可自行修改）",
        "admin_cancel": "取消",
        "admin_confirm": "创建",
        "admin_reset_title": "重置密码",
        "admin_reset_pwd": "新密码",
        "admin_reset_confirm": "确认重置",
        "admin_badge_admin": "管理员",
        "admin_badge_active": "正常",
        "admin_badge_disabled": "已禁用",
        "admin_stats_users": "总用户",
        "admin_stats_active": "活跃用户",
        "admin_stats_persons": "总联系人",
        "admin_stats_relations": "关系链路",
        "admin_never_login": "从未登录",
        "admin_last_login": "最后登录",
        "admin_btn_password": "改密",
        "admin_btn_disable": "禁用",
        "admin_btn_enable": "启用",
        "tag_hometown": "🏠 家乡",
        "tag_school": "🎓 学校",
        "tag_company": "🏢 公司",
        "tag_interest": "❤️ 兴趣",
        "toast_added": "✅ 已添加并自动关联！",
        "toast_select_two": "请选择两个人",
        "toast_provide": "请提供文本或图片",
        "toast_parse": "⏳ AI 解析中...",
        "err_username_short": "用户名至少2个字符",
        "err_username_long": "用户名最多20个字符",
        "err_username_chars": "用户名只能包含中英文、数字和下划线",
        "err_password_length": "密码需要6-16位",
        "err_password_complex": "密码需包含字母和数字",
        "err_password_mismatch": "两次密码不一致",
        "err_user_exists": "用户名已存在",
        "err_login": "用户名或密码错误",
        "err_login_locked": "尝试次数过多，已锁定，请{m}分钟后再试",
        "err_empty_username": "请输入用户名",
        "err_reason_short": "申请理由至少10个字，认真写的申请我都会看",
        "apply_submitted": "申请已提交 ✅ 审核通过后即可登录（通常1天内）",
        "switch_lang": "English",
    },
    "en": {
        "app_title": "KnowNet",
        "page_title": "KnowNet · Graph",
        "count": "{} contacts",
        "search_placeholder": "Search name, tag, school...",
        "add_btn": "+ Add",
        "tab_all": "All",
        "tab_path": "Path",
        "tab_tags": "Tags",
        "modal_add": "Add Contact",
        "upload_hint": "Tap to upload screenshot/business card\nor paste text below",
        "paste_hint": "Or paste notes...\ne.g. John, Jiangxi, Jinan Univ 2010,建材,hobbies:fishing",
        "ai_btn": "🤖 AI Parse & Add",
        "empty_title": "No contacts yet",
        "empty_hint": "Tap '+ Add' to upload\na WeChat screenshot or business card photo",
        "search_network": "🔗 Find shortest path between two people",
        "select_a": "Select first person...",
        "select_b": "Select second person...",
        "find_btn": "🔍 Find Path",
        "no_path": "No path found",
        "found_depth": "Found {} degree connection",
        "same_person": "Same person",
        "no_detail": "No details",
        "interests_label": "Interests",
        "relations_label": "Connections",
        "raw_notes_label": "Raw notes",
        "login_title": "KnowNet · Multi-User",
        "login_username": "Username",
        "login_password": "Password",
        "login_btn": "Sign In",
        "login_register_hint": "New here?",
        "login_register_link": "Create account →",
        "register_title": "Apply for KnowNet",
        "register_username": "Username",
        "register_password": "Password (6-16 chars, letters+digits)",
        "register_password2": "Confirm password",
        "register_btn": "Submit Application",
        "register_login_hint": "Already have an account?",
        "apply_hook": "KnowNet is in limited beta. Tell me who you are and why you need it — I read every serious application.",
        "apply_reason": "Why do you need it? (at least 10 characters)",
        "apply_source": "How did you hear about us? (optional)",
        "apply_after": "You can log in after approval, usually within 1 day.",
        "register_login_link": "Sign In",
        "admin_title": "Admin Panel",
        "admin_back": "← Back",
        "admin_logout": "Logout",
        "admin_users": "👥 Users",
        "admin_applications": "📋 Pending Applications",
        "admin_appl_pending": "Pending",
        "admin_appl_approve": "Approve",
        "admin_appl_reject": "Reject",
        "admin_appl_empty": "No pending applications",
        "admin_create": "+ Create User",
        "admin_create_title": "Create User",
        "admin_create_user": "Username",
        "admin_create_pwd": "Initial password",
        "admin_cancel": "Cancel",
        "admin_confirm": "Create",
        "admin_reset_title": "Reset Password",
        "admin_reset_pwd": "New password",
        "admin_reset_confirm": "Confirm Reset",
        "admin_badge_admin": "Admin",
        "admin_badge_active": "Active",
        "admin_badge_disabled": "Disabled",
        "admin_stats_users": "Total Users",
        "admin_stats_active": "Active",
        "admin_stats_persons": "Contacts",
        "admin_stats_relations": "Links",
        "admin_never_login": "Never logged in",
        "admin_last_login": "Last login",
        "admin_btn_password": "Reset PW",
        "admin_btn_disable": "Disable",
        "admin_btn_enable": "Enable",
        "tag_hometown": "🏠 Hometown",
        "tag_school": "🎓 School",
        "tag_company": "🏢 Company",
        "tag_interest": "❤️ Interests",
        "toast_added": "✅ Added & linked!",
        "toast_select_two": "Select two people",
        "toast_provide": "Please provide text or image",
        "toast_parse": "⏳ AI parsing...",
        "err_username_short": "Username too short (min 2 chars)",
        "err_username_long": "Username too long (max 20 chars)",
        "err_username_chars": "Username: letters, numbers, underscore only",
        "err_password_length": "Password must be 6-16 characters",
        "err_password_complex": "Password needs letters AND numbers",
        "err_password_mismatch": "Passwords don't match",
        "err_user_exists": "Username already taken",
        "err_login": "Invalid username or password",
        "err_login_locked": "Too many attempts. Locked, try again in {m} minutes",
        "err_empty_username": "Please enter username",
        "err_reason_short": "Application reason needs at least 10 characters. Serious applications get reviewed",
        "apply_submitted": "Application submitted ✅ You can log in after approval (usually within 1 day)",
        "switch_lang": "中文",
    }
}

@app.context_processor
def inject_lang():
    lang = session.get("lang", "en")
    # Default to English; user can switch via ?lang=zh or toggle button
    if not lang:
        lang = "en"
    session["lang"] = lang

    def T(key, *args):
        s = LANG.get(lang, LANG["en"]).get(key, key)
        if args:
            s = s.format(*args)
        return s

    return {"T": T, "lang": lang}

@app.before_request
def check_lang_switch():
    lang_param = request.args.get("lang")
    if lang_param in ("zh", "en"):
        session["lang"] = lang_param
        return redirect(url_for(request.endpoint or "index"))

def _T(key, *args):
    """Get translated string for current session language"""
    lang = session.get("lang", "en")
    s = LANG.get(lang, LANG["en"]).get(key, key)
    if args:
        s = s.format(*args)
    return s

# ==================== Auth ====================

from werkzeug.security import generate_password_hash, check_password_hash as _wk_check

def hash_password(pwd):
    """werkzeug scrypt 哈希（抗GPU爆破）"""
    return generate_password_hash(pwd)

def check_password(pwd, stored):
    """校验密码；兼容旧版 SHA256+salt 格式，命中后自动升级为 scrypt"""
    if stored and ":" in stored and len(stored.split(":")) == 2 and not stored.startswith(("scrypt:", "pbkdf2:")):
        # 旧格式 salt:sha256hex
        salt, h = stored.split(":", 1)
        if hashlib.sha256(f"{salt}:{pwd}".encode()).hexdigest() == h:
            return True  # 下次登录时由调用方升级
    return _wk_check(stored, pwd)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"code": 401, "msg": "请先登录"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            return jsonify({"code": 403, "msg": "仅管理员可访问"}), 403
        return f(*args, **kwargs)
    return decorated

# ==================== Database ====================

def get_admin_db():
    """主数据库：只存用户账号"""
    if "admin_db" not in g:
        g.admin_db = sqlite3.connect(MAIN_DB)
        g.admin_db.row_factory = sqlite3.Row
    return g.admin_db

def get_db():
    """用户数据库：每个用户独立的 SQLite 文件"""
    user_id = session.get("user_id")
    if not user_id:
        raise Exception("未登录")
    db_key = f"user_db_{user_id}"
    if db_key not in g:
        db_path = os.path.join(USERDATA_DIR, f"knownet_{user_id}.db")
        g.db_path = db_path
        g.__dict__[db_key] = sqlite3.connect(db_path)
        g.__dict__[db_key].row_factory = sqlite3.Row
        g.__dict__[db_key].execute("PRAGMA journal_mode=WAL")
        # Init user schema if not exists
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                g.__dict__[db_key].executescript(f.read())
            g.__dict__[db_key].commit()
    return g.__dict__[db_key]

@app.teardown_appcontext
def close_db(exception):
    for k in list(g.__dict__.keys()):
        if k.startswith("user_db_") or k == "admin_db":
            db = g.__dict__.pop(k, None)
            if db:
                db.close()

def init_main_db():
    """初始化主数据库（用户表 + 申请表）"""
    db = sqlite3.connect(MAIN_DB)
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    # 申请制：开放注册改为申请-审核（防 API Key 被刷）
    db.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            reason TEXT NOT NULL,
            source TEXT DEFAULT '',
            status INTEGER DEFAULT 0,  -- 0待审 1通过 2拒绝
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()

    # Create default admin if no users exist
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        db.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
                   ("admin", hash_password(KNOWNET_ADMIN_PASSWORD)))
        db.commit()
        print("✅ 默认管理员已创建: admin / REDACTED")
    db.close()

def migrate_old_data():
    """迁移旧版单用户数据 → 用户 ID=1 的独立数据库"""
    old_db = os.path.join(APP_ROOT, "knownet.db")
    target_db = os.path.join(USERDATA_DIR, "knownet_1.db")

    # Check if old data exists and target doesn't
    if not os.path.exists(old_db):
        return
    if os.path.exists(target_db):
        return  # Already migrated

    # Check if old DB has persons table (not just users table)
    check = sqlite3.connect(old_db)
    tables = [r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    check.close()

    if "persons" not in tables:
        return  # Old DB is already just a users table

    # Migrate: rename old DB to user_1's DB
    os.rename(old_db, target_db)
    print(f"✅ 旧数据已迁移 → {target_db}")

# ==================== AI 解析 ====================

EXTRACT_PROMPT = """你是一个信息提取助手。从以下文本/图片中提取人物信息，返回纯JSON（不要markdown代码块）：

{
  "name": "姓名",
  "phone": "手机号（如有）",
  "hometown": "家乡（省/市）",
  "school": "毕业院校",
  "company": "公司/单位",
  "position": "职位",
  "industry": "行业",
  "interests": ["兴趣1","兴趣2"],
  "children": "子女信息（几个孩子，年龄等）",
  "spouse": "配偶信息",
  "other": "其他值得记录的备注"
}

只提取明确提到的信息，不确定的字段用空字符串。interests是数组。"""

def call_deepseek(prompt, text):
    ds_key = ""
    if os.path.exists(DS_KEY_PATH):
        with open(DS_KEY_PATH, "r") as f:
            ds_key = f.read().strip()
    if not ds_key:
        return None

    data = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.3,
        "max_tokens": 800
    }).encode()

    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=data,
        headers={"Authorization": f"Bearer {ds_key}", "Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        content = result["choices"][0]["message"]["content"]
        content = re.sub(r'```\w*\n?', '', content)
        content = content.strip().strip('`')
        return json.loads(content)
    except Exception as e:
        print(f"DeepSeek error: {e}")
        return None

def call_zhipu_vision(image_path, text_prompt=""):
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()

    data = json.dumps({
        "model": "glm-4v-flash",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": text_prompt or "请详细描述图片中所有文字信息和人物信息"}
            ]
        }],
        "max_tokens": 1000
    }).encode()

    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=data,
        headers={"Authorization": f"Bearer {ZHIPU_KEY}", "Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=40)
        result = json.loads(resp.read())
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Zhipu error: {e}")
        return None

def extract_and_save(raw_text, image_path=None):
    text = raw_text or ""

    if image_path:
        ocr_text = call_zhipu_vision(image_path,
            "请逐字读取图片中的所有文字信息，包括姓名、手机号、地区、学校、公司、备注等。如果是微信资料页，请特别关注备注名和标签")
        if ocr_text:
            text = (text + "\n" + ocr_text).strip()

    if not text.strip():
        return None, "未识别到任何文字信息"

    extracted = call_deepseek(EXTRACT_PROMPT, text)
    if not extracted:
        return None, "AI 提取失败，请重试"

    db = get_db()
    name = (extracted.get("name") or "未命名").strip()
    phone = (extracted.get("phone") or "").strip()
    hometown = (extracted.get("hometown") or "").strip()
    school = (extracted.get("school") or "").strip()
    company = (extracted.get("company") or "").strip()
    position = (extracted.get("position") or "").strip()
    industry = (extracted.get("industry") or "").strip()
    interests = extracted.get("interests") or []
    children = (extracted.get("children") or "").strip()
    spouse = (extracted.get("spouse") or "").strip()
    other = (extracted.get("other") or "").strip()

    db.execute(
        """INSERT INTO persons (name, phone, raw_notes, extracted)
           VALUES (?, ?, ?, ?)""",
        (name, phone, text[:2000], json.dumps(extracted, ensure_ascii=False))
    )
    pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    tags_to_add = []
    if hometown:
        tags_to_add.append(("hometown", hometown))
        prov = hometown[:2] if len(hometown) >= 2 else hometown
        if prov != hometown:
            tags_to_add.append(("hometown_province", prov))
    if school:
        tags_to_add.append(("school", school))
    if company:
        tags_to_add.append(("company", company))
    if industry:
        tags_to_add.append(("industry", industry))
    if position:
        tags_to_add.append(("position", position))
    for interest in interests:
        if isinstance(interest, str) and interest.strip():
            tags_to_add.append(("interest", interest.strip()))
    if children:
        tags_to_add.append(("children", children))
    if spouse:
        tags_to_add.append(("spouse", spouse))

    for tag_name, tag_value in tags_to_add:
        try:
            db.execute(
                "INSERT OR IGNORE INTO tags (person_id, tag_name, tag_value) VALUES (?, ?, ?)",
                (pid, tag_name, tag_value)
            )
        except:
            pass

    db.commit()
    auto_link_by_tags(pid)
    return pid, None

def auto_link_by_tags(person_id):
    db = get_db()
    my_tags = db.execute(
        "SELECT tag_name, tag_value FROM tags WHERE person_id=?", (person_id,)
    ).fetchall()

    for tag in my_tags:
        others = db.execute(
            """SELECT DISTINCT person_id FROM tags
               WHERE tag_name=? AND tag_value=? AND person_id!=?""",
            (tag["tag_name"], tag["tag_value"], person_id)
        ).fetchall()
        for other in others:
            rel_type = f"same_{tag['tag_name']}"
            try:
                db.execute(
                    "INSERT OR IGNORE INTO relations (person_a_id, person_b_id, relation_type) VALUES (?, ?, ?)",
                    (person_id, other["person_id"], rel_type)
                )
            except:
                pass
    db.commit()

# ==================== User Routes ====================

@app.route("/")
@login_required
def index():
    return render_template("index.html")

# 登录失败计数（内存级，防爆破；重启清零可接受）
_login_fails = {}  # key: username|ip -> [count, lock_until_ts]

def _login_lock_key(username):
    return f"{username}|{request.remote_addr}"

def _check_locked(username):
    key = _login_lock_key(username)
    rec = _login_fails.get(key)
    if rec and rec[1] > time.time():
        return int(rec[1] - time.time())
    return 0

def _record_fail(username):
    key = _login_lock_key(username)
    rec = _login_fails.get(key, [0, 0])
    rec[0] += 1
    if rec[0] >= 5:
        rec[1] = time.time() + 900  # 5次失败锁15分钟
        rec[0] = 0
    _login_fails[key] = rec

def _clear_fails(username):
    _login_fails.pop(_login_lock_key(username), None)

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        pwd = request.form.get("password", "")
        if not username:
            return render_template("login.html", error=_T("err_empty_username"))

        locked = _check_locked(username)
        if locked > 0:
            return render_template("login.html", error=_T("err_login_locked").format(m=locked // 60 + 1))

        admin_db = get_admin_db()
        user = admin_db.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1", (username,)
        ).fetchone()

        if user and check_password(pwd, user["password_hash"]):
            # 旧哈希命中后自动升级为 scrypt
            if user["password_hash"] and ":" in user["password_hash"] and not user["password_hash"].startswith(("scrypt:", "pbkdf2:")):
                admin_db.execute("UPDATE users SET password_hash=? WHERE id=?",
                                 (hash_password(pwd), user["id"]))
                admin_db.commit()
            _clear_fails(username)
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            admin_db.execute("UPDATE users SET last_login=CURRENT_TIMESTAMP WHERE id=?", (user["id"],))
            admin_db.commit()

            if user["is_admin"] and request.args.get("next") == "admin":
                return redirect(url_for("admin_panel"))
            return redirect(url_for("index"))

        _record_fail(username)
        return render_template("login.html", error=_T("err_login"))

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

@app.route("/register", methods=["GET", "POST"])
def register_page():
    """申请制：提交申请 → 管理员审核 → 通过后登录（不自动登录，防 API Key 被刷）"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        pwd = request.form.get("password", "")
        pwd2 = request.form.get("password2", "")
        reason = request.form.get("reason", "").strip()
        source = request.form.get("source", "").strip()

        # 前端校验的二次确认（防绕过）
        if not username or len(username) < 2:
            return render_template("register.html", error=_T("err_username_short"))
        if len(username) > 20:
            return render_template("register.html", error=_T("err_username_long"))
        if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff]+$', username):
            return render_template("register.html", error=_T("err_username_chars"))
        if len(pwd) < 6 or len(pwd) > 16:
            return render_template("register.html", error=_T("err_password_length"))
        if not re.search(r'[a-zA-Z]', pwd) or not re.search(r'[0-9]', pwd):
            return render_template("register.html", error=_T("err_password_complex"))
        if pwd != pwd2:
            return render_template("register.html", error=_T("err_password_mismatch"))
        if len(reason) < 10:
            return render_template("register.html", error=_T("err_reason_short"))

        admin_db = get_admin_db()
        exists = admin_db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            return render_template("register.html", error=_T("err_user_exists"))
        # 用户名已被申请/待审也拒绝（防重复提交）
        pending = admin_db.execute(
            "SELECT id FROM applications WHERE username=? AND status=0", (username,)
        ).fetchone()
        if pending:
            return render_template("register.html", error=_T("err_user_exists"))

        admin_db.execute(
            "INSERT INTO applications (username, password_hash, reason, source) VALUES (?, ?, ?, ?)",
            (username, hash_password(pwd), reason, source))
        admin_db.commit()

        # 申请提交成功：不自动登录，提示等待审核
        return render_template("register.html", ok=_T("apply_submitted"))

    return render_template("register.html")

# ==================== User API ====================

@app.route("/api/persons", methods=["GET"])
@login_required
def api_persons():
    search = request.args.get("q", "").strip()
    db = get_db()
    if search:
        rows = db.execute(
            """SELECT * FROM persons WHERE name LIKE ? OR phone LIKE ? OR raw_notes LIKE ?
               ORDER BY updated_at DESC LIMIT 50""",
            (f"%{search}%", f"%{search}%", f"%{search}%")
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM persons ORDER BY updated_at DESC LIMIT 50").fetchall()

    result = []
    for r in rows:
        person = dict(r)
        person["extracted"] = json.loads(person["extracted"]) if person["extracted"] else {}
        person["tags"] = [dict(t) for t in db.execute(
            "SELECT * FROM tags WHERE person_id=?", (r["id"],)
        ).fetchall()]
        person["relation_count"] = db.execute(
            "SELECT COUNT(*) as c FROM relations WHERE person_a_id=? OR person_b_id=?", (r["id"], r["id"])
        ).fetchone()["c"]
        result.append(person)

    return jsonify({"code": 0, "data": result})

@app.route("/api/person/<int:pid>", methods=["GET"])
@login_required
def api_person_detail(pid):
    db = get_db()
    r = db.execute("SELECT * FROM persons WHERE id=?", (pid,)).fetchone()
    if not r:
        return jsonify({"code": 404, "msg": "不存在"})
    person = dict(r)
    person["extracted"] = json.loads(person["extracted"]) if person["extracted"] else {}
    person["tags"] = [dict(t) for t in db.execute(
        "SELECT * FROM tags WHERE person_id=?", (pid,)
    ).fetchall()]

    rels = db.execute(
        """SELECT r.*, p1.name as person_a_name, p2.name as person_b_name
           FROM relations r
           JOIN persons p1 ON r.person_a_id=p1.id
           JOIN persons p2 ON r.person_b_id=p2.id
           WHERE r.person_a_id=? OR r.person_b_id=?""",
        (pid, pid)
    ).fetchall()
    person["relations"] = [dict(rl) for rl in rels]

    return jsonify({"code": 0, "data": person})

@app.route("/api/person", methods=["POST"])
@login_required
def api_person_add():
    text = request.form.get("text", "").strip()
    image = request.files.get("image")
    image_path = None

    if image and image.filename:
        ext = os.path.splitext(image.filename)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
            return jsonify({"code": 400, "msg": "仅支持图片格式"})
        fname = f"{uuid.uuid4().hex}{ext}"
        image_path = os.path.join(UPLOAD_DIR, fname)
        image.save(image_path)

    if not text and not image_path:
        return jsonify({"code": 400, "msg": "请提供文本或图片"})

    pid, error = extract_and_save(text, image_path)
    if error:
        return jsonify({"code": 500, "msg": error})

    return jsonify({"code": 0, "msg": "已添加并自动关联", "data": {"id": pid}})

@app.route("/api/search/tag", methods=["GET"])
@login_required
def api_search_tag():
    tag_name = request.args.get("name", "").strip()
    tag_value = request.args.get("value", "").strip()
    if not tag_name:
        return jsonify({"code": 400, "msg": "请提供标签名"})

    db = get_db()
    query = "SELECT DISTINCT tag_value, COUNT(*) as cnt FROM tags WHERE tag_name=? "
    params = [tag_name]
    if tag_value:
        query += "AND tag_value LIKE ? "
        params.append(f"%{tag_value}%")
    query += "GROUP BY tag_value ORDER BY cnt DESC LIMIT 30"
    values = db.execute(query, params).fetchall()

    return jsonify({"code": 0, "data": [dict(v) for v in values]})

@app.route("/api/search/tag/<tag_name>/<path:tag_value>", methods=["GET"])
@login_required
def api_tag_persons(tag_name, tag_value):
    db = get_db()
    rows = db.execute(
        """SELECT p.* FROM persons p JOIN tags t ON p.id=t.person_id
           WHERE t.tag_name=? AND t.tag_value=? ORDER BY p.name""",
        (tag_name, tag_value)
    ).fetchall()

    result = []
    for r in rows:
        person = dict(r)
        person["extracted"] = json.loads(person["extracted"]) if person["extracted"] else {}
        person["tags"] = [dict(t) for t in db.execute(
            "SELECT * FROM tags WHERE person_id=?", (r["id"],)
        ).fetchall()]
        result.append(person)

    return jsonify({"code": 0, "data": result})

@app.route("/api/path/<int:a>/<int:b>", methods=["GET"])
@login_required
def api_find_path(a, b):
    db = get_db()
    max_depth = 6

    all_rels = db.execute("SELECT person_a_id, person_b_id FROM relations").fetchall()
    adj = {}
    for r in all_rels:
        adj.setdefault(r["person_a_id"], set()).add(r["person_b_id"])
        adj.setdefault(r["person_b_id"], set()).add(r["person_a_id"])

    if a not in adj or b not in adj:
        return jsonify({"code": 0, "data": {"path": [], "msg": "未找到关联路径"}})

    from collections import deque
    visited = {a}
    parent = {a: None}
    depth_map = {a: 0}
    queue = deque([a])
    found = False

    while queue and not found:
        node = queue.popleft()
        if depth_map[node] >= max_depth:
            continue  # 超过6层不再扩展（防全图遍历吃内存）
        for neighbor in adj.get(node, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                parent[neighbor] = node
                depth_map[neighbor] = depth_map[node] + 1
                queue.append(neighbor)
                if neighbor == b:
                    found = True
                    break

    if not found:
        return jsonify({"code": 0, "data": {"path": [], "msg": f"未在{max_depth}度内找到路径"}})

    path_ids = []
    node = b
    while node is not None:
        path_ids.insert(0, node)
        node = parent[node]

    path = []
    for i, pid in enumerate(path_ids):
        p = db.execute("SELECT id, name, phone FROM persons WHERE id=?", (pid,)).fetchone()
        shared_tags = []
        if i > 0:
            prev_id = path_ids[i-1]
            shared_tags = [dict(t) for t in db.execute(
                """SELECT DISTINCT t1.tag_name, t1.tag_value FROM tags t1
                   JOIN tags t2 ON t1.tag_name=t2.tag_name AND t1.tag_value=t2.tag_value
                   WHERE t1.person_id=? AND t2.person_id=?""",
                (pid, prev_id)
            ).fetchall()]
        path.append({
            "id": p["id"],
            "name": p["name"],
            "phone": p["phone"],
            "shared_tags": shared_tags
        })

    return jsonify({"code": 0, "data": {"path": path, "depth": len(path)-1}})

@app.route("/api/user/info")
@login_required
def api_user_info():
    return jsonify({"username": session.get("username"), "is_admin": session.get("is_admin")})

# ==================== Admin Panel ====================

@app.route("/admin")
def admin_panel():
    """管理后台：仅管理员可访问"""
    if not session.get("is_admin"):
        return redirect(url_for("login_page", next="admin"))
    return render_template("admin.html")

@app.route("/api/admin/users")
@login_required
@admin_required
def api_admin_users():
    """列出所有用户（仅元数据，不含用户内部数据）"""
    db = get_admin_db()
    users = db.execute(
        "SELECT id, username, is_admin, is_active, created_at, last_login FROM users ORDER BY id"
    ).fetchall()

    result = []
    for u in users:
        user = dict(u)
        # Count user's persons (aggregate only, no actual data)
        user_db_path = os.path.join(USERDATA_DIR, f"knownet_{u['id']}.db")
        try:
            udb = sqlite3.connect(f"file:{user_db_path}?mode=ro", uri=True)
            n_persons = udb.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
            n_tags = udb.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
            n_rels = udb.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
            udb.close()
            user["person_count"] = n_persons
            user["tag_count"] = n_tags
            user["relation_count"] = n_rels
        except:
            user["person_count"] = 0
            user["tag_count"] = 0
            user["relation_count"] = 0
        result.append(user)

    return jsonify({"code": 0, "data": result})

@app.route("/api/admin/applications", methods=["GET"])
@login_required
@admin_required
def api_admin_applications():
    """待审核/已处理申请列表"""
    status = request.args.get("status", 0, type=int)
    db = get_admin_db()
    rows = db.execute(
        "SELECT id, username, reason, source, status, created_at FROM applications WHERE status=? ORDER BY created_at DESC",
        (status,)).fetchall()
    return jsonify({"code": 0, "data": [dict(r) for r in rows]})

@app.route("/api/admin/application/<int:aid>/approve", methods=["POST"])
@login_required
@admin_required
def api_admin_approve_application(aid):
    """通过申请：applications → users（搬数据 + 建独立库）"""
    db = get_admin_db()
    app_row = db.execute("SELECT * FROM applications WHERE id=? AND status=0", (aid,)).fetchone()
    if not app_row:
        return jsonify({"code": 404, "msg": "申请不存在或已处理"})
    exists = db.execute("SELECT id FROM users WHERE username=?", (app_row["username"],)).fetchone()
    if exists:
        db.execute("UPDATE applications SET status=2 WHERE id=?", (aid,))
        db.commit()
        return jsonify({"code": 400, "msg": "用户名已存在，申请已拒绝"})

    cur = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                     (app_row["username"], app_row["password_hash"]))
    uid = cur.lastrowid
    db.execute("UPDATE applications SET status=1 WHERE id=?", (aid,))
    db.commit()
    db.close()

    # 用户独立库懒创建（首次登录时 get_db 自动建 schema），此处无需预建
    return jsonify({"code": 0, "msg": "已通过并创建账号", "data": {"uid": uid}})

@app.route("/api/admin/application/<int:aid>/reject", methods=["POST"])
@login_required
@admin_required
def api_admin_reject_application(aid):
    """拒绝申请"""
    db = get_admin_db()
    db.execute("UPDATE applications SET status=2 WHERE id=? AND status=0", (aid,))
    db.commit()
    return jsonify({"code": 0, "msg": "已拒绝"})

@app.route("/api/admin/user", methods=["POST"])
@login_required
@admin_required
def api_admin_create_user():
    """创建新用户"""
    username = request.json.get("username", "").strip()
    password = request.json.get("password", "").strip()

    if not username or len(username) < 2:
        return jsonify({"code": 400, "msg": "用户名至少2个字符"})
    if len(password) < 6 or len(password) > 16 or not re.search(r'[a-zA-Z]', password) or not re.search(r'[0-9]', password):
        return jsonify({"code": 400, "msg": "密码需6-16位且含字母和数字"})

    db = get_admin_db()
    exists = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if exists:
        return jsonify({"code": 400, "msg": "用户名已存在"})

    db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
               (username, hash_password(password)))
    db.commit()

    return jsonify({"code": 0, "msg": "用户创建成功"})

@app.route("/api/admin/user/<int:uid>/toggle", methods=["POST"])
@login_required
@admin_required
def api_admin_toggle_user(uid):
    """启用/禁用用户"""
    db = get_admin_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        return jsonify({"code": 404, "msg": "用户不存在"})
    if user["is_admin"]:
        return jsonify({"code": 400, "msg": "不能禁用管理员"})

    new_status = 0 if user["is_active"] else 1
    db.execute("UPDATE users SET is_active=? WHERE id=?", (new_status, uid))
    db.commit()

    return jsonify({"code": 0, "msg": "已" + ("启用" if new_status else "禁用")})

@app.route("/api/admin/user/<int:uid>/reset-password", methods=["POST"])
@login_required
@admin_required
def api_admin_reset_password(uid):
    """重置用户密码"""
    new_pwd = request.json.get("password", "").strip()
    if len(new_pwd) < 6 or len(new_pwd) > 16 or not re.search(r'[a-zA-Z]', new_pwd) or not re.search(r'[0-9]', new_pwd):
        return jsonify({"code": 400, "msg": "密码需6-16位且含字母和数字"})

    db = get_admin_db()
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new_pwd), uid))
    db.commit()

    return jsonify({"code": 0, "msg": "密码已重置"})

@app.route("/api/admin/stats")
@login_required
@admin_required
def api_admin_stats():
    """总体统计数据（不含任何用户个人数据）"""
    db = get_admin_db()
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_users = db.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]

    total_persons = 0
    total_relations = 0
    for fname in os.listdir(USERDATA_DIR):
        if fname.startswith("knownet_") and fname.endswith(".db"):
            try:
                path = os.path.join(USERDATA_DIR, fname)
                udb = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                total_persons += udb.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
                total_relations += udb.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
                udb.close()
            except:
                pass

    return jsonify({
        "code": 0,
        "data": {
            "total_users": total_users,
            "active_users": active_users,
            "total_persons": total_persons,
            "total_relations": total_relations
        }
    })

# ==================== 启动 ====================

# 迁移旧数据（如果存在）
migrate_old_data()

# 初始化主数据库（用户表）
init_main_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8200, debug=False)
