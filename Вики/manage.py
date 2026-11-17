"""Wiki CLI: admin bootstrap, password reset, SQLite backup."""
import getpass, re, sys, sqlite3, shutil
from datetime import datetime
from pathlib import Path
import db

# Prevent Windows cp1252 consoles from crashing on Cyrillic status messages.
if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='backslashreplace')

def admin():
    db.init_db()
    print('OBSIDIAN RUSSIA WIKI — создание / обновление администратора')
    name=input('Логин (латиница, 3–32 символа): ').strip()
    if not re.fullmatch('[A-Za-z0-9_-]{3,32}',name):raise SystemExit('Ошибка: недопустимый логин.')
    password=getpass.getpass('Пароль (не меньше 12 символов): ')
    again=getpass.getpass('Повторите пароль: ')
    if password!=again or len(password)<12 or len(password)>256:raise SystemExit('Ошибка: пароль не совпадает или не соответствует требованиям.')
    with db.connect() as c:
        row=c.execute('SELECT id FROM users WHERE username=?',(name,)).fetchone()
        if row:
            c.execute('UPDATE users SET pass_hash=?,role=? WHERE id=?',(db.hash_password(password),'admin',row['id']))
            c.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
            print('Учётная запись обновлена; прежние сессии сброшены.')
        else:
            c.execute('INSERT INTO users(username,pass_hash,role,created_at) VALUES(?,?,?,?)',(name,db.hash_password(password),'admin',db.now()))
            print('Администратор создан.')

def backup():
    db.init_db()
    folder=db.DATA/'backups';folder.mkdir(parents=True,exist_ok=True)
    filepath=folder/('wiki-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
    with db.connect() as source,sqlite3.connect(filepath) as target:source.backup(target)
    print('Резервная копия:',filepath)
    print('Важно: дополнительно сохраните папку static/uploads с изображениями.')

if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in ('admin','backup'):
        print('Использование: python manage.py admin | backup');sys.exit(2)
    {'admin':admin,'backup':backup}[sys.argv[1]]()
