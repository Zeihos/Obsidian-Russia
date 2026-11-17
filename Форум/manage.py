"""Interactive administrator setup; run python manage.py admin."""
import sys,re,getpass,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from db import init_db,connect,hash_password,now,DATA

# Prevent Windows cp1252 consoles from crashing on Cyrillic status messages.
if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='backslashreplace')

def admin():
    init_db()
    print('\nOBSIDIAN RUSSIA — создание или повышение администратора')
    username=input('Логин администратора (3–24 латинских символа, цифры, _): ').strip()
    if not re.fullmatch(r'[A-Za-z0-9_]{3,24}',username):
        raise SystemExit('Некорректный логин')
    with connect() as c:
        existing=c.execute('SELECT id,role FROM users WHERE username=?',(username,)).fetchone()
        if existing:
            confirm=input('Аккаунт уже есть. Повысить его до администратора? [yes]: ').strip()
            if confirm!='yes':raise SystemExit('Отменено')
            c.execute("UPDATE users SET role='admin',banned=0 WHERE id=?",(existing['id'],))
            print('Права администратора выданы. Пароль не изменён.')
            return
        email=input('Email: ').strip().lower()
        if not re.fullmatch(r'[^\s@]{1,64}@[^\s@]{1,180}\.[^\s@]{2,}',email):raise SystemExit('Некорректный email')
        pw=getpass.getpass('Пароль (12+ символов): ')
        pw2=getpass.getpass('Повтори пароль: ')
        if len(pw)<12 or len(pw)>128 or pw!=pw2:raise SystemExit('Пароли не совпадают или слишком короткие')
        try:c.execute("INSERT INTO users(username,email,password_hash,role,joined_at) VALUES (?,?,?,'admin',?)",(username,email,hash_password(pw),now()))
        except sqlite3.IntegrityError:raise SystemExit('Такой email или логин уже используется')
        print('Администратор создан. Используй этот логин для входа на форум.')

def backup():
    init_db()
    out=DATA/'backups'
    out.mkdir(parents=True,exist_ok=True,mode=0o700)
    name=out/f'forum_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")}.sqlite3'
    with connect() as source, sqlite3.connect(name) as dest:
        source.backup(dest)
    print('Резервная копия создана:',name)

if __name__=='__main__':
    if len(sys.argv)==2 and sys.argv[1]=='admin':admin()
    elif len(sys.argv)==2 and sys.argv[1]=='backup':backup()
    else:print('Использование: python manage.py admin | backup')
