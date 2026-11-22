"""SQLite persistence for OBSIDIAN RUSSIA. No third-party dependencies."""
import os, sqlite3, hashlib, hmac, secrets, datetime, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv('OBSIDIAN_DATA_DIR', str(ROOT / 'data')))
DB_FILE = DATA_DIR / 'obsidian.sqlite3'
UTC = datetime.timezone.utc

def now():
    return datetime.datetime.now(UTC).isoformat(timespec='seconds')

def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not DB_FILE.exists():
        # SQLite normally creates files respecting the process umask (often 0644).
        DB_FILE.touch(mode=0o600, exist_ok=True)
    c = sqlite3.connect(DB_FILE, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=15000')
    c.execute('PRAGMA journal_mode=WAL')
    return c

def setting(c, key, default=''):
    r = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return r['value'] if r else default

def settings(c):
    return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM settings')}

def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           username TEXT NOT NULL UNIQUE COLLATE NOCASE,
           email TEXT NOT NULL UNIQUE COLLATE NOCASE,
           password_hash TEXT NOT NULL,
           auth_version INTEGER NOT NULL DEFAULT 0,
           email_verified_at TEXT DEFAULT NULL,
           role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
           created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (
           token_hash TEXT PRIMARY KEY,
           user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
           csrf TEXT NOT NULL,
           expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS news (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           title TEXT NOT NULL, excerpt TEXT NOT NULL, body TEXT NOT NULL,
           category TEXT NOT NULL DEFAULT 'Новости',
           published INTEGER NOT NULL DEFAULT 1,
           created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS servers (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
           address TEXT NOT NULL DEFAULT '',
           online INTEGER NOT NULL DEFAULT 0,
           capacity INTEGER NOT NULL DEFAULT 0,
           status TEXT NOT NULL DEFAULT 'soon' CHECK(status IN ('soon','online','offline')),
           updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
           subject TEXT NOT NULL, message TEXT NOT NULL,
           status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
           created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS account_security_events (
           id INTEGER PRIMARY KEY AUTOINCREMENT,
           user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
           event TEXT NOT NULL,
           created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_security_events_user
           ON account_security_events(user_id,id);
        CREATE TABLE IF NOT EXISTS settings (
           key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_news_pub ON news(published,created_at);
        CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets(user_id,created_at);
        CREATE TABLE IF NOT EXISTS sso_codes (
           code_hash TEXT PRIMARY KEY,
           client_id TEXT NOT NULL,
           user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
           expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL
         );
         CREATE TABLE IF NOT EXISTS email_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            pending_email TEXT NOT NULL,
            purpose TEXT NOT NULL CHECK(purpose IN ('verify','change')),
            expires_at TEXT NOT NULL,
            UNIQUE(user_id, purpose)
         );
         CREATE INDEX IF NOT EXISTS idx_email_tokens_expiry ON email_tokens(expires_at);
         CREATE INDEX IF NOT EXISTS idx_password_resets_expiry ON password_resets(expires_at);
         CREATE INDEX IF NOT EXISTS idx_sso_codes_expiry ON sso_codes(expires_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
        ''')
        # Upgrade in-place: never recreate or overwrite existing user data.
        user_columns={r['name'] for r in c.execute('PRAGMA table_info(users)')}
        if 'auth_version' not in user_columns:
            c.execute('ALTER TABLE users ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0')
        # Existing addresses are not automatically trusted: ownership was never proven.
        if 'email_verified_at' not in user_columns:
            c.execute('ALTER TABLE users ADD COLUMN email_verified_at TEXT DEFAULT NULL')
        defaults = {
          'vk':'https://vk.ru/obsidian_brussia',
          'telegram':'https://t.me/obsidian_brussia',
          'forum':'', 'android_download':'', 'windows_download':'',
          'site_notice':'Мы готовим новый игровой мир OBSIDIAN RUSSIA. Следи за анонсами!',
          'support_email':'', 'donation_url':'',
        }
        for k,v in defaults.items():
            c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)',(k,v))
        if c.execute('SELECT COUNT(*) FROM news').fetchone()[0] == 0:
            t=now()
            c.execute('INSERT INTO news(title,excerpt,body,category,published,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',(
                'OBSIDIAN RUSSIA — новый этап начинается',
                'Мы готовим собственный RolePlay-мир. Узнай, каким будет наш проект и где следить за новостями.',
                'Добро пожаловать в OBSIDIAN RUSSIA! Мы создаём новую игровую вселенную со своей атмосферой, сообществом и большими планами.\n\nНа этом сайте будут появляться новости разработки, сведения о серверах и инструкции для игроков.\n\nПока проект находится в подготовке. Официальные даты запуска и ссылки на игровые клиенты будут опубликованы после подтверждения командой.',
                'Разработка',1,t,t))
        if c.execute('SELECT COUNT(*) FROM servers').fetchone()[0] == 0:
            c.execute('INSERT INTO servers(name,description,status,updated_at) VALUES (?,?,?,?)',(
                'OBSIDIAN #01','Первый игровой мир проекта. Информация о запуске появится позднее.','soon',now()))

def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,260000)
    return 'pbkdf2_sha256$260000$'+salt.hex()+'$'+key.hex()

def check_password(password, encoded):
    try:
        algo, count, salt, wanted=encoded.split('$')
        if algo!='pbkdf2_sha256' or not 100000 <= int(count) <= 1000000: return False
        candidate=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),int(count))
        return hmac.compare_digest(candidate,bytes.fromhex(wanted))
    except (ValueError,TypeError): return False

def new_token(c, user_id=None):
    # Anonymous sessions are created during ordinary browsing: purge expired rows.
    c.execute('DELETE FROM sessions WHERE expires_at<=?', (now(),))
    token=secrets.token_urlsafe(36)
    csrf=secrets.token_urlsafe(24)
    expiry=(datetime.datetime.now(UTC)+datetime.timedelta(days=7)).isoformat(timespec='seconds')
    c.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',(
        hashlib.sha256(token.encode()).hexdigest(),user_id,csrf,expiry))
    return token

def get_session(c, token):
    if not token or len(token)>256: return None
    return c.execute('''SELECT s.token_hash,s.user_id,s.csrf,s.expires_at,
        u.username,u.role,u.email,u.email_verified_at,u.created_at FROM sessions s LEFT JOIN users u ON u.id=s.user_id
        WHERE s.token_hash=? AND s.expires_at>?''',(
        hashlib.sha256(token.encode()).hexdigest(),now())).fetchone()
