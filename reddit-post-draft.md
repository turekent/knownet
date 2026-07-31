# Reddit 帖子草稿

---

## 📍 目标板块：r/selfhosted
## 🕐 最佳发布时间：北京时间周二到周四晚上 9-11 点（美东上午 9-11 点）
## 🏷️ 附加可交叉发布：r/CRM、r/SideProject

---

## 📝 标题（二选一）

**A（痛点导向，推荐）：**
> I was tired of manually typing 10 fields per contact in Monica, so I built an AI-powered alternative that reads WeChat screenshots

**B（简洁对比）：**
> KnowNet — An AI-powered personal CRM that reads screenshots instead of making you fill forms (like Monica + OCR + knowledge graph)

---

## 📄 正文

---

I've tried Monica. I really wanted to love it.

The idea of a personal CRM is brilliant — remembering birthdays, last conversations, kids' names, how you met. But after adding 30 contacts, I burned out. Ten fields per person. Every. Single. Time.

The breaking point was a dinner party. I met 8 new people. Came home with 8 WeChat screenshots. Opened Monica. Stared at the form. Closed it.

That night I asked myself: **why can't I just paste the screenshot and have AI do the rest?**

So I built KnowNet.

### What it does:

1. **You take a screenshot** (WeChat profile, business card photo, chat summary)
2. **AI reads it** — Zhipu GLM-4V extracts all text, DeepSeek structures it
3. **Auto-tags everything** — hometown, school, company, industry, interests
4. **Auto-builds your network** — people with the same school/hometown/city get linked automatically
5. **6-degree path search** — "How do I reach Person X through my existing network?"

Zero manual data entry. Take a photo, it's in your knowledge graph.

### Tech stack (dead simple):
- Python + Flask + SQLite (one file to back up)
- AI: Zhipu GLM-4V (vision OCR) → DeepSeek (structure extraction)
- BFS graph algorithm for path finding
- Mobile-first PWA (works on your phone browser)

### Why not just use Monica?
Monica is great if you enjoy curating a database. KnowNet is for people who want the database to build itself from the stuff already on their phone.

| | Monica | KnowNet |
|---|---|---|
| Adding a contact | Fill 10+ fields | 📸 Screenshot → Done |
| WeChat screenshots | ❌ Not supported | ✅ Native support |
| Auto-tagging | ❌ | ✅ Hometown, school, company, interests |
| Knowledge graph | ❌ Flat list | ✅ Auto-linked network |
| 6-degree path search | ❌ | ✅ BFS up to depth 6 |
| Deployment | PHP + MySQL + Composer | Python + SQLite (1 command) |

### Demo
[Link to demo GIF — add after recording]

### Try it
- **GitHub**: https://github.com/YOUR_USERNAME/knownet
- **Live demo**: https://knownet.digitalmind.chat

One command to run locally:
```bash
pip install -r requirements.txt && python app.py
```

Would love feedback from this community. What features would make this actually useful for your workflow?

---

## ⚠️ 发布前检查清单

- [ ] 把 `YOUR_USERNAME` 替换为实际 GitHub 用户名
- [ ] 录制 demo GIF 并上传到 GitHub README
- [ ] 确认 `knownet.digitalmind.chat` 可访问
- [ ] 检查 GitHub repo 有 README + LICENSE + requirements.txt
- [ ] 准备好回复评论（真诚互动，不要复制粘贴）

---

## 💬 常见评论的预准备回复

**Q: "Why not just use Monica?"**
> Monica is excellent for what it does. But it's designed for manual curation — the author himself describes it as "your personal journal." KnowNet takes the opposite approach: capture-first, organize-later. Different philosophies for different people.

**Q: "Is this China-only because of WeChat?"**
> The WeChat integration is the killer feature, but it works with any screenshot or photo. Business cards, LinkedIn profiles, conference badges — anything with text on it. The vision model is language-agnostic.

**Q: "Privacy concerns with sending screenshots to AI APIs?"**
> Valid concern. The image goes to Zhipu's API for OCR only — no storage. Text goes to DeepSeek for structuring. Both are stateless. If you're handling highly sensitive contacts, you can swap in a local LLaVA model for the vision step.

**Q: "Why SQLite instead of Postgres?"**
> Because I wanted `cp knownet.db backup.db` to be the entire backup strategy. For a personal tool with <10,000 contacts, SQLite in WAL mode handles it perfectly.

---

## 📢 发帖后 24 小时行动计划

1. **前 2 小时**：守在帖子旁，回复每一条评论（Reddit 算法在初期互动最重要）
2. **12 小时后**：如果帖子沉了，交叉发布到 r/SideProject（换一个标题角度）
3. **48 小时后**：整理所有反馈 → 更新 GitHub Issues → 发一篇"Thanks r/selfhosted! Here's what I'm building next"

---

## 🎯 目标

- 第一天：50-100 upvotes，30+ 评论
- 第一周：200+ GitHub stars
- 第一月：Product Hunt launch（积累足够反馈后）
