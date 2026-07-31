-- 人脉知识图谱 v1

CREATE TABLE IF NOT EXISTS persons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    wechat_id TEXT DEFAULT '',
    avatar_url TEXT DEFAULT '',
    raw_notes TEXT DEFAULT '',
    extracted JSON DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id INTEGER NOT NULL,
    tag_name TEXT NOT NULL,
    tag_value TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_id) REFERENCES persons(id),
    UNIQUE(person_id, tag_name, tag_value)
);

CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(tag_name);
CREATE INDEX IF NOT EXISTS idx_tags_value ON tags(tag_value);
CREATE INDEX IF NOT EXISTS idx_tags_person ON tags(person_id);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_a_id INTEGER NOT NULL,
    person_b_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'acquaintance',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (person_a_id) REFERENCES persons(id),
    FOREIGN KEY (person_b_id) REFERENCES persons(id),
    UNIQUE(person_a_id, person_b_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_rel_a ON relations(person_a_id);
CREATE INDEX IF NOT EXISTS idx_rel_b ON relations(person_b_id);
