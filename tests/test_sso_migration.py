"""In-place SSO schema migrations must retain existing accounts and links."""
import os
from pathlib import Path
from contextlib import closing
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]


def upgrade(folder, env):
    run=subprocess.run(
        [sys.executable,"-c","import db; db.init_db()"],
        cwd=ROOT/folder,env=env,capture_output=True,text=True,timeout=25,
    )
    if run.returncode!=0:
        raise AssertionError(run.stdout+"\n"+run.stderr)


class LegacySSOMigrationTest(unittest.TestCase):
    def test_site_old_users_survive_new_auth_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"site"
            path.mkdir()
            dbfile=path/"obsidian.sqlite3"
            with closing(sqlite3.connect(dbfile)) as conn, conn:
                conn.execute("""
                    CREATE TABLE users(
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       username TEXT NOT NULL UNIQUE,
                       email TEXT NOT NULL UNIQUE,
                       password_hash TEXT NOT NULL,
                       role TEXT NOT NULL DEFAULT 'user',
                       created_at TEXT NOT NULL)
                """)
                conn.execute(
                    "INSERT INTO users(id,username,email,password_hash,role,created_at) "
                    "VALUES(17,'OldSiteUser','old@example.invalid','legacy-hash','user','2026-10-01')"
                )
            env=os.environ.copy()
            env["OBSIDIAN_DATA_DIR"]=str(path)
            upgrade("Сайт",env)
            upgrade("Сайт",env)  # idempotence
            with closing(sqlite3.connect(dbfile)) as conn, conn:
                row=conn.execute(
                    "SELECT id,username,password_hash,auth_version FROM users WHERE id=17"
                ).fetchone()
                self.assertEqual(row,(17,"OldSiteUser","legacy-hash",0))

    def test_forum_legacy_link_survives_auth_version_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"forum"
            path.mkdir()
            dbfile=path/"forum.sqlite3"
            with closing(sqlite3.connect(dbfile)) as conn, conn:
                conn.execute("""
                    CREATE TABLE sso_accounts(
                       provider_sub TEXT PRIMARY KEY,
                       user_id INTEGER NOT NULL UNIQUE)
                """)
                conn.execute(
                    "INSERT INTO sso_accounts(provider_sub,user_id) VALUES('17',42)"
                )
            env=os.environ.copy()
            env["OBFORUM_DATA_DIR"]=str(path)
            upgrade("Форум",env)
            upgrade("Форум",env)
            with closing(sqlite3.connect(dbfile)) as conn, conn:
                row=conn.execute(
                    "SELECT provider_sub,user_id,auth_version FROM sso_accounts"
                ).fetchone()
                self.assertEqual(row,("17",42,0))

    def test_existing_sso_login_states_survive_purpose_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"forum"
            path.mkdir()
            dbfile=path/"forum.sqlite3"
            with closing(sqlite3.connect(dbfile)) as conn, conn:
                conn.execute(
                    "CREATE TABLE sso_states("
                    "state_hash TEXT PRIMARY KEY,session_hash TEXT NOT NULL,expires_at TEXT NOT NULL)"
                )
                conn.execute(
                    "INSERT INTO sso_states(state_hash,session_hash,expires_at) "
                    "VALUES('legacy-state','legacy-session','2099-01-01T00:00:00+00:00')"
                )
            env=os.environ.copy()
            env["OBFORUM_DATA_DIR"]=str(path)
            upgrade("Форум",env)
            upgrade("Форум",env)
            with closing(sqlite3.connect(dbfile)) as conn:
                row=conn.execute(
                    "SELECT state_hash,session_hash,purpose,user_id FROM sso_states"
                ).fetchone()
                self.assertEqual(row,("legacy-state","legacy-session","login",None))


if __name__=="__main__":
    unittest.main()
