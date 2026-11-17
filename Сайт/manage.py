"""Create first administrator from a local, interactive terminal."""
import getpass, sys
from db import connect,init_db,hash_password,now

def main():
    init_db()
    print('OBSIDIAN RUSSIA — настройка администратора')
    print('Команда выполняется только на вашем компьютере/сервере.')
    username=input('Логин администратора: ').strip()
    email=input('Email администратора: ').strip().lower()
    pw=getpass.getpass('Пароль (минимум 12 символов): ')
    again=getpass.getpass('Повторите пароль: ')
    if not (3<=len(username)<=24 and username.replace('_','').isalnum() and 5<=len(email)<=120 and '@' in email and len(pw)>=12 and pw==again):
        print('Ошибка данных: логин 3–24 символа, действительный email, совпадающие пароли от 12 символов.')
        sys.exit(1)
    with connect() as c:
        existing = c.execute('SELECT id,role FROM users WHERE username=? OR email=?',(username,email)).fetchone()
        if existing:
            if existing['role']=='admin': print('Администратор с такими данными уже есть.'); return
            print('Такой логин или email уже занят.'); sys.exit(1)
        c.execute('INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',(
            username,email,hash_password(pw),'admin',now()))
        print('Администратор создан. Войдите на /login и откройте /admin.')
if __name__=='__main__':main()
