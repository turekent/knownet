#!/usr/bin/env python3
"""人脉知识图谱 - 手机端 AI 驱动个人关系管理"""
import os, json, uuid, base64, datetime, sqlite3, re, urllib.request
from flask import Flask, request, jsonify, render_template, g, session

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_ROOT, "knownet.db")
SCHEMA_PATH = os.path.join(APP_ROOT, "schema.sql")
UPLOAD_DIR = os.path.join(APP_ROOT, "static", "uploads")

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
os.makedirs(UPLOAD_DIR, exist_ok=True)

# API Keys
DS_KEY_PATH = "/home/ubuntu/.ds_key"
ZHIPU_KEY = "REDACTED"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    with app.app_context():
        db = get_db()
        if os.path.exists(SCHEMA_PATH):
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                db.executescript(f.read())
            db.commit()

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
    """DeepSeek 文本提取"""
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
        # Clean up markdown code blocks
        content = re.sub(r'```\w*\n?', '', content)
        content = content.strip().strip('`')
        return json.loads(content)
    except Exception as e:
        print(f"DeepSeek error: {e}")
        return None

def call_zhipu_vision(image_path, text_prompt=""):
    """智谱 GLM-4V 图片识别"""
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
    """统一提取入口：图片 OCR → DeepSeek 解析 → 入库"""
    text = raw_text or ""

    # Step 1: 如果有图片，先用智谱读图
    if image_path:
        ocr_text = call_zhipu_vision(image_path,
            "请逐字读取图片中的所有文字信息，包括姓名、手机号、地区、学校、公司、备注等。如果是微信资料页，请特别关注备注名和标签")
        if ocr_text:
            text = (text + "\n" + ocr_text).strip()

    if not text.strip():
        return None, "未识别到任何文字信息"

    # Step 2: DeepSeek 结构化提取
    extracted = call_deepseek(EXTRACT_PROMPT, text)
    if not extracted:
        return None, "AI 提取失败，请重试"

    # Step 3: 入库
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

    # Step 4: 自动打标签
    tags_to_add = []
    if hometown:
        tags_to_add.append(("hometown", hometown))
        # 自动提取省份
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

    # Step 5: 自动发现关系（同标签的人自动关联）
    auto_link_by_tags(pid)

    return pid, None

def auto_link_by_tags(person_id):
    """基于共同标签自动建立关系"""
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

# ==================== API ====================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/persons", methods=["GET"])
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
def api_person_detail(pid):
    db = get_db()
    r = db.execute("SELECT * FROM persons WHERE id=?", (pid,)).fetchone()
    if not r:
        return jsonify({"code": 404, "msg": "不存在"})
    person = dict(r)
    person["extracted"] = json.loads(person["extracted"]) if person["extracted"] else {}

    # Tags
    person["tags"] = [dict(t) for t in db.execute(
        "SELECT * FROM tags WHERE person_id=?", (pid,)
    ).fetchall()]

    # Relations with names
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
def api_person_add():
    """添加人物：支持图片上传或纯文本"""
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
def api_search_tag():
    """按标签搜索"""
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
def api_tag_persons(tag_name, tag_value):
    """获取某个标签下的所有人"""
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
def api_find_path(a, b):
    """BFS 找两个人之间的最短关系路径（六度人脉）"""
    db = get_db()
    max_depth = 6

    # Build adjacency list
    all_rels = db.execute("SELECT person_a_id, person_b_id FROM relations").fetchall()
    adj = {}
    for r in all_rels:
        adj.setdefault(r["person_a_id"], set()).add(r["person_b_id"])
        adj.setdefault(r["person_b_id"], set()).add(r["person_a_id"])

    if a not in adj or b not in adj:
        return jsonify({"code": 0, "data": {"path": [], "msg": "未找到关联路径"}})

    # BFS
    from collections import deque
    visited = {a}
    parent = {a: None}
    queue = deque([a])
    found = False

    while queue and not found:
        node = queue.popleft()
        for neighbor in adj.get(node, set()):
            if neighbor not in visited:
                visited.add(neighbor)
                parent[neighbor] = node
                queue.append(neighbor)
                if neighbor == b:
                    found = True
                    break

    if not found:
        return jsonify({"code": 0, "data": {"path": [], "msg": f"未在{max_depth}度内找到路径"}})

    # Reconstruct path
    path_ids = []
    node = b
    while node is not None:
        path_ids.insert(0, node)
        node = parent[node]

    # Get person names and shared tags
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

# ==================== 启动 ====================

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8200, debug=False)
