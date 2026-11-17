"""Persistent models for OBSIDIAN RUSSIA forum (SQLite, stdlib only)."""
import os, re, hmac, secrets, sqlite3, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv('OBFORUM_DATA_DIR', str(ROOT / 'data')))
DB = DATA / 'forum.sqlite3'

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connect():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not DB.exists(): DB.touch(mode=0o600, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 20000')
    conn.execute('PRAGMA journal_mode = WAL')
    return conn

SECTIONS = [
 ('Официальный раздел','Объявления команды и основная информация',[
  ('Новости проекта','Последние новости и заявления руководства',1),
  ('Правила форума','Правила общения, поведения и публикаций',1),
  ('Вопросы и ответы','Помощь новым участникам и ответы на вопросы',0)]),
 ('Игровые серверы','Обсуждение игры OBSIDIAN RUSSIA',[
  ('Общение игроков','Знакомства, игровые истории и общение',0),
  ('Предложения и идеи','Предлагайте улучшения для сервера и сообщества',0),
  ('Ошибки и неполадки','Сообщения о найденных игровых ошибках',0)]),
 ('Жалобы и обращения','Официальная подача обращений',[
  ('Жалобы на игроков','Жалобы с доказательствами нарушений',0),
  ('Жалобы на администрацию','Обжалование действий представителей команды',0),
  ('Обжалование наказаний','Заявления на пересмотр игрового наказания',0),
  ('Техническая поддержка','Вопросы доступа, установки и работы игры',0)]),
 ('Организации и набор','Набор сотрудников и управление игровыми структурами',[
  ('Государственные организации','Фракционные объявления и заявки',0),
  ('Нелегальные организации','Семьи, группировки и объединения игроков',0),
  ('Вакансии проекта','Заявки в команду и сведения о наборе',1)]),
 ('Сообщество','Общение и творчество участников',[
  ('Свободное общение','Темы вне игровых разделов',0),
  ('Медиа и творчество','Скриншоты, видеоролики и пользовательские работы',0)])
]

def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
         id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL COLLATE NOCASE,
         email TEXT UNIQUE NOT NULL COLLATE NOCASE, password_hash TEXT NOT NULL,
         role TEXT NOT NULL DEFAULT 'member' CHECK(role IN ('member','moderator','admin')),
         banned INTEGER NOT NULL DEFAULT 0, joined_at TEXT NOT NULL,
         about TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS sessions (
         token_hash TEXT PRIMARY KEY,
         user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
         csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS categories (
         id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
         sort_order INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS forums (
         id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL REFERENCES categories(id),
         name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
         sort_order INTEGER NOT NULL DEFAULT 0, staff_only INTEGER NOT NULL DEFAULT 0,
         archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS threads (
         id INTEGER PRIMARY KEY, forum_id INTEGER NOT NULL REFERENCES forums(id),
         user_id INTEGER NOT NULL REFERENCES users(id),
         title TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL,
         updated_at TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
         locked INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0,
         views INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS posts (
         id INTEGER PRIMARY KEY, thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
         user_id INTEGER NOT NULL REFERENCES users(id), body TEXT NOT NULL,
         created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
         deleted INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reports (
         id INTEGER PRIMARY KEY, reporter_id INTEGER NOT NULL REFERENCES users(id),
         post_id INTEGER REFERENCES posts(id),
         thread_id INTEGER REFERENCES threads(id),
         reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
         created_at TEXT NOT NULL, closed_by INTEGER REFERENCES users(id),
         closed_at TEXT,
         CHECK((post_id IS NOT NULL) != (thread_id IS NOT NULL)));
        CREATE TABLE IF NOT EXISTS follows (
         user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
         thread_id INTEGER NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
         last_seen TEXT NOT NULL, PRIMARY KEY(user_id,thread_id));
        CREATE TABLE IF NOT EXISTS audit (
         id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
         action TEXT NOT NULL, target TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_threads_forum ON threads(forum_id,deleted,pinned,updated_at);
        CREATE INDEX IF NOT EXISTS idx_posts_thread ON posts(thread_id,deleted,created_at);
        CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status,created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_follows_thread ON follows(thread_id);
        ''')
        if c.execute('SELECT COUNT(*) FROM categories').fetchone()[0] == 0:
            for i, (title, description, forums) in enumerate(SECTIONS):
                cid=c.execute('INSERT INTO categories(title,description,sort_order) VALUES (?,?,?)',(title,description,i)).lastrowid
                for j, (name, desc, staff) in enumerate(forums):
                    c.execute('INSERT INTO forums(category_id,name,description,sort_order,staff_only) VALUES (?,?,?,?,?)',(cid,name,desc,j,staff))

def hash_password(value):
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',value.encode('utf-8'),salt,360000)
    return f'pbkdf2_sha256$360000${salt.hex()}${digest.hex()}'

def verify_password(value, encoded):
    try:
        name, count, salt, digest=encoded.split('$')
        count=int(count)
        if name!='pbkdf2_sha256' or not (200000<=count<=800000):return False
        got=hashlib.pbkdf2_hmac('sha256',value.encode('utf-8'),bytes.fromhex(salt),count)
        return hmac.compare_digest(got,bytes.fromhex(digest))
    except (ValueError,TypeError):return False

def create_session(c,user_id=None):
    token=secrets.token_urlsafe(40)
    expires=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(timespec='seconds')
    c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES (?,?,?,?)',(
        hashlib.sha256(token.encode()).hexdigest(),user_id,secrets.token_urlsafe(32),expires))
    return token

def session_for(c,token):
    if not token or len(token)>256:return None
    return c.execute('''SELECT s.token_hash,s.user_id,s.csrf,u.username,u.role,u.email,u.banned,u.joined_at,u.about
        FROM sessions s LEFT JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>?''',(hashlib.sha256(token.encode()).hexdigest(),now())).fetchone()

def audit(c,actor,action,target):
    c.execute('INSERT INTO audit(actor_id,action,target,created_at) VALUES (?,?,?,?)',(actor,action,str(target)[:150],now()))
