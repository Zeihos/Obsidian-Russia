"""OBSIDIAN RUSSIA — standalone discussion forum. Python 3.12+, no packages.
Local: python app.py; admin: python manage.py admin
Production: put a TLS reverse proxy in front, set OBFORUM_SECURE_COOKIE=1,
OBFORUM_BASE_URL=https://your-domain.example and run a managed service.
"""
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import sys
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict,deque
from contextlib import closing
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

import db
import views as v
import sso

ROOT=Path(__file__).resolve().parent
STATIC=(ROOT/'static').resolve()
HOST=os.getenv('OBFORUM_BIND','127.0.0.1')
PORT=int(os.getenv('OBFORUM_PORT','8090'))
SECURE=os.getenv('OBFORUM_SECURE_COOKIE','0')=='1'
BASE_URL=os.getenv('OBFORUM_BASE_URL',f'http://localhost:{PORT}').rstrip('/')
BODY_LIMIT=220_000
LOCK=threading.Lock()
RATE=defaultdict(deque)

MESSAGES={
 'welcome':'Добро пожаловать на форум OBSIDIAN RUSSIA!',
 'registered':'Аккаунт создан. Добро пожаловать!',
 'bye':'Вы вышли из аккаунта.',
 'saved':'Изменения успешно сохранены.',
 'posted':'Ответ опубликован.',
 'created':'Тема опубликована.',
 'deleted':'Публикация удалена.',
 'reported':'Жалоба отправлена команде модерации.',
 'subscribed':'Подписка на тему обновлена.',
  'sessions':'Другие входы на форум завершены.',
 'error':'Не удалось выполнить действие. Проверь данные и повтори попытку.',
 'exists':'Этот логин или email уже зарегистрирован.',
 'password':'Неверный логин или пароль.',
 'confirm':'Пароли не совпадают или слишком короткие.',
 'rate':'Слишком много запросов. Повтори действие позднее.',
 'login':'Авторизуйся, чтобы продолжить.',
 'forbidden':'Недостаточно прав для выполнения действия.',
}

class Invalid(Exception):
    pass


def ratelimit(ip,kind,limit=12,window=900):
    current=time.monotonic()
    with LOCK:
        key=(ip,kind); arr=RATE[key]
        while arr and arr[0]<current-window:arr.popleft()
        if len(arr)>=limit:return False
        arr.append(current)
        if len(RATE)>15000:
            for k in list(RATE)[:2000]:
                if not RATE[k] or RATE[k][-1]<current-window:RATE.pop(k,None)
        return True


def go(path):
    if not path.startswith('/') or path.startswith('//') or '\\' in path or '\r' in path or '\n' in path:return '/'
    return path


def positive(text,default=1,limit=999):
    try:return max(1,min(limit,int(text)))
    except (TypeError,ValueError):return default


def number(value):
    try:return int(value)
    except (TypeError,ValueError):return 0


class Handler(BaseHTTPRequestHandler):
    server_version='ObsidianForum/1.0'
    sys_version=''

    def log_message(self,fmt,*args):
        logging.info('%s - %s',self.address_string(),fmt%args)

    def respond(self,body,status=200,ctype='text/html; charset=utf-8',cookie=None,headers=None):
        c=getattr(self,'conn',None)
        if c is not None:c.commit()
        if isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if SECURE:self.send_header('Strict-Transport-Security','max-age=31536000; includeSubDomains')
        self.send_header('Cache-Control','public, max-age=3600' if ctype.startswith(('image/','text/css','text/javascript','application/javascript')) else 'no-store')
        if cookie is not None:
            secure='; Secure' if SECURE else ''
            if cookie:self.send_header('Set-Cookie',f'obforum_session={cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age=604800{secure}')
            else:self.send_header('Set-Cookie',f'obforum_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{secure}')
        for k,val in (headers or {}).items():self.send_header(k,val)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)

    def redirect(self,path,cookie=None):
        self.respond(b'',303,'text/plain; charset=utf-8',cookie,{'Location':go(path)})

    def error_page(self,code,message):
        self.respond(v.layout('Ошибка',f'<div class="notfound"><span>{code}</span><h1>ОШИБКА</h1><p>{v.E(message)}</p><a class="btn btn-red" href="/">На главную</a></div>'),code)

    def read_session(self,c,create=False):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:pass
        token=cookie['obforum_session'].value if 'obforum_session' in cookie else ''
        sess=db.session_for(c,token)
        if sess:return sess,None
        if create:
            token=db.create_session(c)
            return db.session_for(c,token),token
        return None,None

    def user_for(self,s):
        return s if s is not None and s['user_id'] is not None and not s['banned'] else None

    def form(self):
        if not self.headers.get('Content-Type','').lower().startswith('application/x-www-form-urlencoded'):
            raise Invalid('Ожидалась стандартная HTML-форма.')
        try:
            length=int(self.headers.get('Content-Length','-1'))
            if length<0 or length>BODY_LIMIT:raise Invalid('Форма слишком большая.')
            raw=self.rfile.read(length)
            if len(raw)!=length:raise Invalid('Форма не была получена полностью.')
            params=parse_qs(raw.decode('utf-8','strict'),keep_blank_values=True,max_num_fields=30)
            return {k:(values[0] if values else '') for k,values in params.items()}
        except (ValueError,UnicodeDecodeError):raise Invalid('Неверная кодировка или формат формы.')

    def do_HEAD(self):return self.do_GET()

    def do_GET(self):
        self.conn=None
        try:self.get()
        except (BrokenPipeError,ConnectionResetError):pass
        except Invalid as e:
            self.conn=None
            self.error_page(400,str(e))
        except Exception:
            logging.exception('GET %s',self.path)
            self.conn=None
            try:self.error_page(500,'Внутренняя ошибка. Попробуй снова позже.')
            except Exception:pass
        finally:
            if self.conn:
                try:self.conn.close()
                except Exception:pass

    def get(self):
        url=urlsplit(self.path);path=url.path;args=parse_qs(url.query)
        if path=='/health':return self.respond(json.dumps({'ok':True,'app':'obsidian-forum'}),ctype='application/json; charset=utf-8')
        if path=='/robots.txt':return self.respond('User-agent: *\nDisallow: /admin\nDisallow: /account\nDisallow: /login\nDisallow: /register\n',ctype='text/plain; charset=utf-8')
        if path.startswith('/static/'):
            filename=(STATIC/path[len('/static/'):]).resolve()
            if not filename.is_relative_to(STATIC) or not filename.is_file():return self.error_page(404,'Файл не найден.')
            if filename.suffix.lower() not in {'.png','.jpg','.jpeg','.svg','.css','.js','.webp'}:return self.error_page(403,'Недопустимый тип файла.')
            return self.respond(filename.read_bytes(),ctype=mimetypes.guess_type(str(filename))[0] or 'application/octet-stream')
        with closing(db.connect()) as c, c:
            self.conn=c
            sess,token=self.read_session(c,True)
            user=self.user_for(sess)
            csrf=sess['csrf']
            message=MESSAGES.get(args.get('message',[''])[0],'')
            page=positive(args.get('page',[1])[0])
            status=200
            if path=='/sso/login':
                if not sso.enabled():
                    return self.error_page(404,'Единый вход пока не настроен.')
                if user:
                    return self.redirect('/account',token)
                link=sso.start(c,sess['token_hash'])
                return self.respond(b'',303,'text/plain; charset=utf-8',token,{'Location':link})
            if path=='/sso/callback':
                if not sso.enabled():
                    return self.error_page(404,'Единый вход пока не настроен.')
                state=args.get('state',[''])[0]
                code=args.get('code',[''])[0]
                if not sess or not sso.consume_state(c,state,sess['token_hash']):
                    return self.error_page(400,'Неверный или просроченный запрос авторизации.')
                c.commit()  # Consume state before contacting the website.
                identity=sso.exchange(code)
                if not identity:
                    return self.error_page(401,'Не удалось подтвердить единый вход. Попробуй снова.')
                user_id=sso.forum_user(c,*identity)
                if not user_id:
                    return self.error_page(403,'Учётная запись недоступна.')
                c.execute('DELETE FROM sessions WHERE token_hash=?',(sess['token_hash'],))
                new_token=db.create_session(c,user_id)
                return self.redirect('/account?message=welcome',new_token)
            if path=='/':title='Главная';body=v.home(c,user)
            elif path=='/latest' or path=='/search':
                q=(args.get('q',[''])[0] if path=='/search' else '').strip()[:80]
                cond='AND (t.title LIKE ? ESCAPE \'\\\' OR t.body LIKE ? ESCAPE \'\\\')' if path=='/search' else ''
                pat='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                values=(pat,pat) if path=='/search' else ()
                total=c.execute('SELECT COUNT(*) FROM threads t WHERE t.deleted=0 '+cond,values).fetchone()[0]
                rows=c.execute('''SELECT t.*,u.username,u.role,f.name AS forum_name,
                 (SELECT COUNT(*) FROM posts p WHERE p.thread_id=t.id AND p.deleted=0) AS replies
                 FROM threads t JOIN users u ON u.id=t.user_id JOIN forums f ON f.id=t.forum_id WHERE t.deleted=0 '''+cond+' ORDER BY t.updated_at DESC,t.id DESC LIMIT 20 OFFSET ?',(*values,(page-1)*20)).fetchall()
                title='Поиск' if path=='/search' else 'Новые темы'
                body=v.latest_page(c,rows,total,page,user,'search' if path=='/search' else 'latest',q)
            elif path=='/members':title='Участники';body=v.member_list(c)
            elif re.fullmatch(r'/user/\d{1,9}',path):
                u=c.execute('SELECT id,username,role,joined_at FROM users WHERE id=? AND banned=0',(number(path.split('/')[-1]),)).fetchone()
                if not u:return self.error_page(404,'Участник не найден.')
                title=u['username'];body=v.user_profile(c,u)
            elif re.fullmatch(r'/forum/\d{1,9}',path):
                f=c.execute('SELECT * FROM forums WHERE id=?',(number(path.split('/')[-1]),)).fetchone()
                if not f or f['archived']:return self.error_page(404,'Раздел не найден.')
                total=c.execute('SELECT COUNT(*) FROM threads WHERE forum_id=? AND deleted=0',(f['id'],)).fetchone()[0]
                rows=c.execute('''SELECT t.*,u.username,u.role,(SELECT COUNT(*) FROM posts p WHERE p.thread_id=t.id AND p.deleted=0) AS replies
                    FROM threads t JOIN users u ON u.id=t.user_id WHERE t.forum_id=? AND t.deleted=0
                    ORDER BY t.pinned DESC,t.updated_at DESC,t.id DESC LIMIT 20 OFFSET ?''',(f['id'],(page-1)*20)).fetchall()
                title=f['name'];body=v.listing(c,f,rows,total,page,user)
            elif path=='/thread/new':
                if not user:return self.redirect('/login?message=login',token)
                forum_id=positive(args.get('forum',[0])[0],0)
                f=c.execute('SELECT * FROM forums WHERE id=?',(forum_id,)).fetchone()
                if not f or f['archived']:return self.error_page(404,'Раздел не найден.')
                if f['staff_only'] and user['role']=='member':return self.error_page(403,'В этом разделе публикует только команда проекта.')
                title='Новая тема';body=v.new_thread_form(f,csrf)
            elif re.fullmatch(r'/thread/\d{1,9}/edit',path):
                tid=number(path.split('/')[2]);t=c.execute('SELECT * FROM threads WHERE id=? AND deleted=0',(tid,)).fetchone()
                if not t:return self.error_page(404,'Тема не найдена.')
                if not user or (user['user_id']!=t['user_id'] and user['role']=='member'):return self.error_page(403,'Недостаточно прав.')
                f=c.execute('SELECT * FROM forums WHERE id=?',(t['forum_id'],)).fetchone()
                title='Редактирование темы';body=v.new_thread_form(f,csrf,t)
            elif re.fullmatch(r'/thread/\d{1,9}',path):
                tid=number(path.split('/')[2]);t=c.execute('''SELECT t.*,u.username,u.role,f.name AS forum_name FROM threads t
                   JOIN users u ON u.id=t.user_id JOIN forums f ON f.id=t.forum_id WHERE t.id=? AND t.deleted=0''',(tid,)).fetchone()
                if not t:return self.error_page(404,'Тема не найдена.')
                count=c.execute('SELECT COUNT(*) FROM posts WHERE thread_id=? AND deleted=0',(tid,)).fetchone()[0]
                posts=c.execute('''SELECT p.*,u.username,u.role FROM posts p JOIN users u ON u.id=p.user_id
                  WHERE p.thread_id=? AND p.deleted=0 ORDER BY p.id ASC LIMIT 20 OFFSET ?''',(tid,(page-1)*20)).fetchall()
                c.execute('UPDATE threads SET views=views+1 WHERE id=?',(tid,))
                # Read-your-own-write not used by page: no static fake views.
                title=t['title'];body=v.thread_page(c,t,posts,count,page,user,csrf)
            elif re.fullmatch(r'/post/\d{1,9}/edit',path):
                p=c.execute('''SELECT p.*,t.deleted AS thread_deleted FROM posts p JOIN threads t ON t.id=p.thread_id WHERE p.id=?''',(number(path.split('/')[2]),)).fetchone()
                if not p or p['deleted'] or p['thread_deleted']:return self.error_page(404,'Ответ не найден.')
                if not user or (p['user_id']!=user['user_id'] and user['role']=='member'):return self.error_page(403,'Недостаточно прав.')
                title='Редактирование ответа';body=v.edit_post_form(p,csrf)
            elif path=='/report':
                if not user:return self.redirect('/login?message=login',token)
                tid=number(args.get('thread',['0'])[0]);pid=number(args.get('post',['0'])[0])
                if (tid>0)==(pid>0):return self.error_page(400,'Укажи публикацию для жалобы.')
                if tid and not c.execute('SELECT 1 FROM threads WHERE id=? AND deleted=0',(tid,)).fetchone():return self.error_page(404,'Публикация не найдена.')
                if pid and not c.execute('SELECT 1 FROM posts p JOIN threads t ON t.id=p.thread_id WHERE p.id=? AND p.deleted=0 AND t.deleted=0',(pid,)).fetchone():return self.error_page(404,'Публикация не найдена.')
                title='Сообщить о нарушении';body=v.report_form(tid,pid,csrf)
            elif path=='/login':
                if user:return self.redirect('/account',token)
                title='Вход';body=v.auth_form('login',csrf)
                if sso.enabled():
                    body='<div class="panel form-card"><a class="btn btn-red" href="/sso/login">Войти через аккаунт OBSIDIAN RUSSIA</a><p>Без передачи пароля форуму. Существующий аккаунт форума останется отдельным.</p></div>'+body
            elif path=='/register':
                if user:return self.redirect('/account',token)
                title='Регистрация';body=v.auth_form('register',csrf)
            elif path=='/account':
                if not user:return self.redirect('/login?message=login',token)
                title='Мой профиль';body=v.account(c,user,csrf)
            elif path=='/admin':
                if not user or user['role']=='member':return self.error_page(403,'Доступ только для команды.')
                tab=args.get('tab',['overview'])[0]
                if tab not in ('overview','reports','threads','users','forums','audit'):tab='overview'
                if user['role']!='admin' and tab in ('users','forums','audit'):return self.error_page(403,'Доступ только для администратора.')
                title='Панель управления';body=v.admin_page(c,user,csrf,tab)
            elif path=='/rules':title='Правила';body=v.rules()
            elif path=='/privacy':title='Конфиденциальность';body=v.privacy()
            elif path=='/api/stats':
                return self.respond(json.dumps(v.stats(c),ensure_ascii=False),ctype='application/json; charset=utf-8')
            elif path=='/api/latest':
                data=[{'id':t['id'],'title':t['title'],'updated_at':t['updated_at']} for t in v.latest_threads(c,10)]
                return self.respond(json.dumps({'threads':data},ensure_ascii=False),ctype='application/json; charset=utf-8')
            else:return self.error_page(404,'Страница не найдена.')
            self.respond(v.layout(title,body,path,user,csrf,message),status,cookie=token)

    def do_POST(self):
        self.conn=None
        try:self.post()
        except (BrokenPipeError,ConnectionResetError):pass
        except Invalid as e:
            self.conn=None
            self.error_page(400,str(e))
        except sqlite3.IntegrityError:
            logging.info('Integrity conflict on %s',self.path)
            self.conn=None
            try:self.redirect('/register?message=exists')
            except Exception:pass
        except Exception:
            logging.exception('POST %s',self.path)
            self.conn=None
            try:self.error_page(500,'Действие не удалось выполнить. Попробуй позже.')
            except Exception:pass
        finally:
            if self.conn:
                try:self.conn.close()
                except Exception:pass

    def post(self):
        path=urlsplit(self.path).path
        f=self.form()
        with closing(db.connect()) as c, c:
            self.conn=c
            s,_=self.read_session(c,False)
            if s is None or not hmac.compare_digest(f.get('csrf',''),s['csrf']):raise Invalid('Форма устарела или токен безопасности неверный. Обнови страницу.')
            user=self.user_for(s)
            ip=self.client_address[0]
            if path=='/login':
                if not ratelimit(ip,'login',12,900):return self.redirect('/login?message=rate')
                identity=f.get('identity','').strip();password=f.get('password','')
                if len(identity)>200 or len(password)>128:return self.redirect('/login?message=password')
                u=c.execute('SELECT * FROM users WHERE username=? OR email=?',(identity,identity)).fetchone()
                if not u or u['banned'] or not db.verify_password(password,u['password_hash']):
                    if not u:db.hash_password('dummy')
                    return self.redirect('/login?message=password')
                c.execute('DELETE FROM sessions WHERE token_hash=?',(s['token_hash'],))
                token=db.create_session(c,u['id'])
                return self.redirect('/account?message=welcome',token)
            if path=='/register':
                if not ratelimit(ip,'register',5,3600):return self.redirect('/register?message=rate')
                username=f.get('username','').strip()
                email=f.get('email','').strip().lower()
                password=f.get('password','');confirm=f.get('confirm','')
                if not re.fullmatch(r'[A-Za-z0-9_]{3,24}',username) or not re.fullmatch(r'[^\s@]{1,64}@[^\s@]{1,180}\.[^\s@]{2,}',email) or len(email)>200:
                    return self.redirect('/register?message=error')
                if password!=confirm or not (10<=len(password)<=128):return self.redirect('/register?message=confirm')
                ident=c.execute('INSERT INTO users(username,email,password_hash,joined_at) VALUES (?,?,?,?)',(
                    username,email,db.hash_password(password),db.now())).lastrowid
                c.execute('DELETE FROM sessions WHERE token_hash=?',(s['token_hash'],))
                token=db.create_session(c,ident)
                return self.redirect('/account?message=registered',token)
            if path=='/logout':
                c.execute('DELETE FROM sessions WHERE token_hash=?',(s['token_hash'],))
                return self.redirect('/?message=bye','')
            if not user:return self.redirect('/login?message=login')
            uid=user['user_id'];staff=user['role'] in ('admin','moderator');admin=user['role']=='admin'
            if path=='/account/sessions/close-others':
                c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,s['token_hash']))
                db.audit(c,uid,'close_other_sessions',uid)
                return self.redirect('/account?message=sessions')
            if path=='/account/sessions/logout-all':
                c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
                db.audit(c,uid,'logout_all_sessions',uid)
                return self.redirect('/?message=bye','')
            if path=='/account/password':
                if c.execute('SELECT 1 FROM sso_accounts WHERE user_id=?',(uid,)).fetchone():
                    return self.error_page(403,'Пароль связанного аккаунта изменяется на основном сайте.')
                if not ratelimit(ip,'pass',10,900):return self.redirect('/account?message=rate')
                old=f.get('old','');pw=f.get('password','')
                r=c.execute('SELECT password_hash FROM users WHERE id=?',(uid,)).fetchone()
                if not r or not db.verify_password(old,r['password_hash']) or not (10<=len(pw)<=128):return self.redirect('/account?message=error')
                c.execute('UPDATE users SET password_hash=? WHERE id=?',(db.hash_password(pw),uid))
                c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,s['token_hash']))
                db.audit(c,uid,'change_password',uid)
                return self.redirect('/account?message=saved')
            if path=='/thread/new':
                if not ratelimit(ip,'threads',20,3600):return self.redirect('/?message=rate')
                fid=number(f.get('forum'));title=f.get('title','').strip();body=f.get('body','').strip()
                forum=c.execute('SELECT * FROM forums WHERE id=?',(fid,)).fetchone()
                if not forum or forum['archived']:return self.error_page(404,'Раздел отсутствует.')
                if forum['staff_only'] and not staff:return self.error_page(403,'Публикация разрешена только команде.')
                if not (5<=len(title)<=130 and 10<=len(body)<=20000):return self.error_page(400,'Название должно быть 5–130 символов, текст — 10–20000 символов.')
                cur=c.execute('INSERT INTO threads(forum_id,user_id,title,body,created_at,updated_at) VALUES (?,?,?,?,?,?)',(
                    fid,uid,title,body,db.now(),db.now()))
                return self.redirect(f'/thread/{cur.lastrowid}?message=created')
            match=re.fullmatch(r'/thread/(\d{1,9})/reply',path)
            if match:
                if not ratelimit(ip,'replies',50,3600):return self.redirect('/?message=rate')
                tid=int(match[1]);body=f.get('body','').strip()
                t=c.execute('SELECT id,locked,deleted FROM threads WHERE id=?',(tid,)).fetchone()
                if not t or t['deleted']:return self.error_page(404,'Тема не найдена.')
                if t['locked']:return self.error_page(403,'Тема закрыта для ответов.')
                if not (2<=len(body)<=10000):return self.error_page(400,'Ответ должен содержать 2–10000 символов.')
                cur=c.execute('INSERT INTO posts(thread_id,user_id,body,created_at,updated_at) VALUES (?,?,?,?,?)',(tid,uid,body,db.now(),db.now()))
                c.execute('UPDATE threads SET updated_at=? WHERE id=?',(db.now(),tid))
                return self.redirect(f'/thread/{tid}?message=posted#post-{cur.lastrowid}')
            match=re.fullmatch(r'/thread/(\d{1,9})/edit',path)
            if match:
                tid=int(match[1]);t=c.execute('SELECT * FROM threads WHERE id=? AND deleted=0',(tid,)).fetchone()
                if not t:return self.error_page(404,'Тема не найдена.')
                if t['user_id']!=uid and not staff:return self.error_page(403,'Нет доступа к этой теме.')
                title=f.get('title','').strip();body=f.get('body','').strip()
                if not (5<=len(title)<=130 and 10<=len(body)<=20000):return self.error_page(400,'Неверная длина заголовка или текста.')
                c.execute('UPDATE threads SET title=?,body=?,updated_at=? WHERE id=?',(title,body,db.now(),tid))
                db.audit(c,uid,'edit_thread',tid)
                return self.redirect(f'/thread/{tid}?message=saved')
            match=re.fullmatch(r'/post/(\d{1,9})/edit',path)
            if match:
                pid=int(match[1]);p=c.execute('''SELECT p.*,t.deleted AS td FROM posts p JOIN threads t ON t.id=p.thread_id WHERE p.id=?''',(pid,)).fetchone()
                if not p or p['deleted'] or p['td']:return self.error_page(404,'Ответ не найден.')
                if p['user_id']!=uid and not staff:return self.error_page(403,'Нельзя редактировать чужой ответ.')
                body=f.get('body','').strip()
                if not (2<=len(body)<=10000):return self.error_page(400,'Текст ответа должен содержать 2–10000 символов.')
                c.execute('UPDATE posts SET body=?,updated_at=? WHERE id=?',(body,db.now(),pid))
                db.audit(c,uid,'edit_post',pid)
                return self.redirect(f'/thread/{p["thread_id"]}?message=saved#post-{pid}')
            match=re.fullmatch(r'/post/(\d{1,9})/delete',path)
            if match:
                pid=int(match[1]);p=c.execute('SELECT * FROM posts WHERE id=?',(pid,)).fetchone()
                if not p:return self.error_page(404,'Ответ не найден.')
                if p['user_id']!=uid and not staff:return self.error_page(403,'Нет доступа к этому ответу.')
                c.execute('UPDATE posts SET deleted=1 WHERE id=?',(pid,))
                db.audit(c,uid,'delete_post',pid)
                return self.redirect(f'/thread/{p["thread_id"]}?message=deleted')
            match=re.fullmatch(r'/thread/(\d{1,9})/follow',path)
            if match:
                tid=int(match[1]);t=c.execute('SELECT id FROM threads WHERE id=? AND deleted=0',(tid,)).fetchone()
                if not t:return self.error_page(404,'Тема не найдена.')
                followed=c.execute('SELECT 1 FROM follows WHERE thread_id=? AND user_id=?',(tid,uid)).fetchone()
                if followed:c.execute('DELETE FROM follows WHERE thread_id=? AND user_id=?',(tid,uid))
                else:c.execute('INSERT INTO follows(user_id,thread_id,last_seen) VALUES (?,?,?)',(uid,tid,db.now()))
                return self.redirect(f'/thread/{tid}?message=subscribed')
            if path=='/report':
                if not ratelimit(ip,'reports',10,3600):return self.redirect('/?message=rate')
                tid=number(f.get('thread_id'));pid=number(f.get('post_id'));reason=f.get('reason','').strip()
                if (tid>0)==(pid>0) or not (10<=len(reason)<=1500):return self.error_page(400,'Проверь публикацию и причину жалобы.')
                if tid:
                    if not c.execute('SELECT 1 FROM threads WHERE id=? AND deleted=0',(tid,)).fetchone():return self.error_page(404,'Публикация не найдена.')
                elif not c.execute('SELECT 1 FROM posts p JOIN threads t ON t.id=p.thread_id WHERE p.id=? AND p.deleted=0 AND t.deleted=0',(pid,)).fetchone():return self.error_page(404,'Публикация не найдена.')
                c.execute('INSERT INTO reports(reporter_id,thread_id,post_id,reason,created_at) VALUES (?,?,?,?,?)',(
                    uid,tid or None,pid or None,reason,db.now()))
                return self.redirect('/account?message=reported')
            # All remaining routes must be staff-only.
            if not staff:return self.error_page(403,'Недостаточно прав.')
            match=re.fullmatch(r'/moderate/thread/(\d{1,9})/(pin|lock|delete|restore)',path)
            if match:
                tid=int(match[1]);action=match[2]
                t=c.execute('SELECT * FROM threads WHERE id=?',(tid,)).fetchone()
                if not t:return self.error_page(404,'Тема не найдена.')
                if action=='pin':c.execute('UPDATE threads SET pinned=1-pinned WHERE id=?',(tid,))
                if action=='lock':c.execute('UPDATE threads SET locked=1-locked WHERE id=?',(tid,))
                if action=='delete':c.execute('UPDATE threads SET deleted=1 WHERE id=?',(tid,))
                if action=='restore':c.execute('UPDATE threads SET deleted=0 WHERE id=?',(tid,))
                db.audit(c,uid,'moderate_'+action,tid)
                return self.redirect(('/admin?tab=threads&message=saved' if action in ('delete','restore') else f'/thread/{tid}?message=saved'))
            match=re.fullmatch(r'/admin/report/(\d{1,9})/close',path)
            if match:
                rid=int(match[1]);c.execute("UPDATE reports SET status='closed',closed_by=?,closed_at=? WHERE id=? AND status='open'",(uid,db.now(),rid))
                db.audit(c,uid,'close_report',rid)
                return self.redirect('/admin?tab=reports&message=saved')
            if not admin:return self.error_page(403,'Нужны права администратора.')
            match=re.fullmatch(r'/admin/user/(\d{1,9})',path)
            if match:
                tid=int(match[1]);role=f.get('role','');ban=int(f.get('banned','')=='1')
                if role not in ('member','moderator','admin'):return self.error_page(400,'Неизвестная роль.')
                target=c.execute('SELECT * FROM users WHERE id=?',(tid,)).fetchone()
                if not target:return self.error_page(404,'Пользователь не найден.')
                if tid==uid and (ban or role!='admin'):return self.error_page(400,'Нельзя заблокировать или понизить собственный аккаунт.')
                if target['role']=='admin' and (role!='admin' or ban):
                    active=c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND banned=0").fetchone()[0]
                    if active<=1:return self.error_page(400,'Нельзя отключить последнего администратора.')
                c.execute('UPDATE users SET role=?,banned=? WHERE id=?',(role,ban,tid))
                if ban:c.execute('DELETE FROM sessions WHERE user_id=?',(tid,))
                db.audit(c,uid,'set_user',f'{tid} -> {role},banned={ban}')
                return self.redirect('/admin?tab=users&message=saved')
            match=re.fullmatch(r'/admin/forum/(\d{1,9})',path)
            if match:
                fid=int(match[1]);name=f.get('name','').strip();desc=f.get('description','').strip()
                if not (3<=len(name)<=90 and len(desc)<=240):return self.error_page(400,'Некорректное название или описание.')
                if not c.execute('SELECT 1 FROM forums WHERE id=?',(fid,)).fetchone():return self.error_page(404,'Раздел не найден.')
                c.execute('UPDATE forums SET name=?,description=?,staff_only=?,archived=? WHERE id=?',(
                    name,desc,int(f.get('staff_only')=='1'),int(f.get('archived')=='1'),fid))
                db.audit(c,uid,'edit_forum',fid)
                return self.redirect('/admin?tab=forums&message=saved')
            match=re.fullmatch(r'/admin/category/(\d{1,9})',path)
            if match:
                cid=int(match[1]);name=f.get('title','').strip();desc=f.get('description','').strip()
                if not (3<=len(name)<=90 and len(desc)<=240):return self.error_page(400,'Некорректное название или описание категории.')
                if not c.execute('SELECT 1 FROM categories WHERE id=?',(cid,)).fetchone():return self.error_page(404,'Категория не найдена.')
                c.execute('UPDATE categories SET title=?,description=? WHERE id=?',(name,desc,cid))
                db.audit(c,uid,'edit_category',cid)
                return self.redirect('/admin?tab=forums&message=saved')
            if path=='/admin/category/new':
                name=f.get('title','').strip();desc=f.get('description','').strip()
                if not (3<=len(name)<=90 and len(desc)<=240):return self.error_page(400,'Некорректное название или описание категории.')
                sort=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM categories').fetchone()[0]
                cid=c.execute('INSERT INTO categories(title,description,sort_order) VALUES (?,?,?)',(name,desc,sort)).lastrowid
                db.audit(c,uid,'create_category',cid)
                return self.redirect('/admin?tab=forums&message=created')
            if path=='/admin/forum/new':
                cid=number(f.get('category_id'));name=f.get('name','').strip();desc=f.get('description','').strip()
                if not (3<=len(name)<=90 and len(desc)<=240):return self.error_page(400,'Некорректные данные раздела.')
                if not c.execute('SELECT 1 FROM categories WHERE id=?',(cid,)).fetchone():return self.error_page(404,'Категория не найдена.')
                sort=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM forums WHERE category_id=?',(cid,)).fetchone()[0]
                new=c.execute('INSERT INTO forums(category_id,name,description,sort_order) VALUES (?,?,?,?)',(cid,name,desc,sort)).lastrowid
                db.audit(c,uid,'create_forum',new)
                return self.redirect('/admin?tab=forums&message=created')
            return self.error_page(404,'Действие не найдено.')


def main():
    # Preserve readable terminal output on Windows and avoid cp1252 startup failures.
    if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    if not (1<=PORT<=65535):raise SystemExit('Некорректный порт.')
    db.init_db()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    with db.connect() as c:
        c.execute('DELETE FROM sessions WHERE expires_at<?',(db.now(),))
        count=c.execute('SELECT COUNT(*) FROM users WHERE role="admin" AND banned=0').fetchone()[0]
    if not count:print('ВНИМАНИЕ: нет администратора. Выполни admin-setup.bat или python manage.py admin')
    if HOST not in ('127.0.0.1','localhost','::1') and not SECURE:raise SystemExit('Публичный HTTP без TLS запрещён. Используй HTTPS reverse proxy и OBFORUM_SECURE_COOKIE=1.')
    print(f'OBSIDIAN RUSSIA — Forum v1.0 | http://localhost:{PORT} | data: {db.DB}')
    http=ThreadingHTTPServer((HOST,PORT),Handler)
    http.serve_forever()

if __name__=='__main__':main()
