"""OBSIDIAN RUSSIA website — Python standard library + SQLite.
Run: python server.py (Python 3.10+). Admin: python manage.py.
"""
import sys
import os, re, json, time, hmac, secrets, sqlite3, threading, hashlib, logging, mimetypes
from collections import defaultdict, deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, urlencode
from http.cookies import SimpleCookie
from html import escape
from db import init_db, connect, now, new_token, get_session, hash_password, check_password, setting, settings
import views as v
import sso
import recovery
import email_verify
import security_events

ROOT=Path(__file__).resolve().parent
STATIC=(ROOT/'static').resolve()
HOST=os.getenv('OBSIDIAN_BIND','127.0.0.1')
PORT=int(os.getenv('OBSIDIAN_PORT','8080'))
SECURE=os.getenv('OBSIDIAN_SECURE_COOKIES','0')=='1'
BASE_URL=os.getenv('OBSIDIAN_BASE_URL',f'http://localhost:{PORT}').rstrip('/')
TRUST_PROXY=os.getenv('OBSIDIAN_TRUST_PROXY','0')=='1'
BODY_LIMIT=64_000
_lock=threading.Lock()
_attempts=defaultdict(deque)

class BadRequest(Exception):pass

def allowed(ip,key,max_hits=12,window=600):
    # In-memory limits are supplemental and reset on restart.
    t=time.monotonic();k=(ip,key)
    with _lock:
        q=_attempts[k]
        while q and q[0]<t-window:q.popleft()
        if len(q)>=max_hits: return False
        q.append(t)
        if len(_attempts)>10000:
            for old in list(_attempts)[:1000]:
                if not _attempts[old] or _attempts[old][-1]<t-window:_attempts.pop(old,None)
        return True

def valid_url(value):
    if not value:return True
    if len(value)>500:return False
    try:
        x=urlsplit(value)
        return x.scheme=='https' and bool(x.netloc) and not x.username and not x.password and not any(ord(k)<32 for k in value)
    except ValueError:return False

def safe_return(route):
    return route if route.startswith('/') and not route.startswith('//') and '\\' not in route else '/'

class Handler(BaseHTTPRequestHandler):
    server_version='ObsidianWeb/1.0'
    sys_version=''

    def client_ip(self):
        # Never trust spoofed X-Forwarded-For from direct public connections.
        remote=self.client_address[0]
        if TRUST_PROXY and remote in ('127.0.0.1','::1'):
            forwarded=self.headers.get('X-Forwarded-For','').split(',')[0].strip()
            if forwarded and len(forwarded)<70 and all(ch in '0123456789abcdefABCDEF:.' for ch in forwarded):
                return forwarded
        return remote

    def log_message(self,fmt,*args):
        # Recovery URLs contain credentials: never record them in logs.
        log_line=fmt%args
        log_line=re.sub(r'(?i)token=[A-Za-z0-9_-]+','token=[REDACTED]',log_line)
        logging.info('%s %s', self.address_string(),log_line)

    def response(self, body, status=200, content='text/html; charset=utf-8', cookie=None, extra=None):
        # Commit before sending redirects; the browser may follow them immediately.
        connection=getattr(self,'_db_connection',None)
        if connection is not None: connection.commit()
        if isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',content)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer' if urlsplit(self.path).path in ('/reset','/verify-email') else 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        if SECURE:self.send_header('Strict-Transport-Security','max-age=31536000; includeSubDomains')
        # Cache only versioned/public static resources, never SSO, sessions or API responses.
        is_static = urlsplit(self.path).path.startswith('/static/')
        self.send_header('Cache-Control','public, max-age=3600' if is_static and status == 200 else 'no-store')
        if cookie is not None:
            extra_opts='; Secure' if SECURE else ''
            self.send_header('Set-Cookie',f'or_session={cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age={7*86400}{extra_opts}' if cookie else f'or_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{extra_opts}')
        for k,val in (extra or {}).items():self.send_header(k,val)
        self.end_headers()
        if self.command != 'HEAD':self.wfile.write(body)

    def redirect(self,path,cookie=None):
        self.response(b'',303,'text/plain; charset=utf-8',cookie,{'Location':safe_return(path)})

    def session_from_request(self,c,create=False):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception: pass
        token=cookie['or_session'].value if 'or_session' in cookie else ''
        s=get_session(c,token)
        if s:return s,None
        if create:
            token=new_token(c)
            return get_session(c,token),token
        return None,None

    def form(self):
        if not self.headers.get('Content-Type','').startswith('application/x-www-form-urlencoded'):
            raise BadRequest('Неверный тип формы.')
        try:
            length=int(self.headers.get('Content-Length', '0'))
            if length<0 or length>BODY_LIMIT:raise BadRequest('Форма слишком большая.')
            raw=self.rfile.read(length)
            if len(raw)!=length:raise BadRequest('Не удалось прочитать форму.')
            parsed=parse_qs(raw.decode('utf-8','strict'),keep_blank_values=True,max_num_fields=30)
            return {key:(values[0] if values else '') for key,values in parsed.items()}
        except (ValueError,UnicodeDecodeError): raise BadRequest('Неверный формат формы.')

    def error_page(self,code,title,desc):
        body=f'<section class="section"><div class="shell not-found"><span>{code}</span><h1>{v.E(title)}</h1><p>{v.E(desc)}</p><a class="btn btn-primary" href="/">Вернуться на главную</a></div></section>'
        self.response(v.layout(title,body),code)

    def do_HEAD(self):self.do_GET()

    def do_GET(self):
        self._db_connection=None
        try: self.handle_get()
        except (BrokenPipeError,ConnectionResetError): pass
        except Exception:
            logging.exception('GET failed')
            try:self.error_page(500,'ОШИБКА СЕРВЕРА','Попробуйте позже.')
            except Exception:pass

    def handle_get(self):
        path=urlsplit(self.path).path
        qs=parse_qs(urlsplit(self.path).query)
        if path=='/health':return self.response(json.dumps({'ok':True,'service':'obsidian-russia'}),200,'application/json; charset=utf-8')
        if path.startswith('/static/'):
            # Resolve and limit static paths to our own directory.
            filename=(STATIC/path[len('/static/'):]).resolve()
            if not filename.is_relative_to(STATIC) or not filename.is_file():return self.error_page(404,'НЕ НАЙДЕНО','Файл отсутствует.')
            content=mimetypes.guess_type(filename.name)[0] or 'application/octet-stream'
            return self.response(filename.read_bytes(),200,content)
        if path=='/robots.txt':
            return self.response('User-agent: *\nDisallow: /admin\nDisallow: /account\nDisallow: /login\nDisallow: /register\nDisallow: /contact\nSitemap: '+BASE_URL+'/sitemap.xml\n',200,'text/plain; charset=utf-8')
        if path=='/sitemap.xml':
            paths=['','/about','/play','/servers','/news','/donate','/rules','/privacy','/contact']
            site=''.join(f'<url><loc>{escape(BASE_URL+p)}</loc></url>' for p in paths)
            return self.response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+site+'</urlset>',200,'application/xml; charset=utf-8')
        if path=='/api/status':
            with connect() as c:
                servers=[dict(s) for s in c.execute('SELECT id,name,address,online,capacity,status,updated_at FROM servers ORDER BY id')]
            # Report the most recent admin update, not the request time as data freshness.
            last_update=max((item['updated_at'] for item in servers if item['updated_at']),default=None)
            return self.response(json.dumps({'servers':servers,'source':'admin_manual','updated_at':last_update},ensure_ascii=False),200,'application/json; charset=utf-8')
        if path=='/api/news':
            with connect() as c:
                articles=[dict(n) for n in c.execute('SELECT id,title,excerpt,category,created_at FROM news WHERE published=1 ORDER BY created_at DESC,id DESC LIMIT 30')]
            return self.response(json.dumps({'news':articles},ensure_ascii=False),200,'application/json; charset=utf-8')
        with connect() as c:
            self._db_connection=c
            session,new_cookie=self.session_from_request(c,True)
            user=session if session['user_id'] else None
            csrf=session['csrf']
            config=settings(c)
            statuses={'saved':'Изменения сохранены.','created':'Запись создана.','deleted':'Запись удалена.',
                      'ticket':'Обращение отправлено.','password':'Пароль обновлён.','bye':'Вы вышли из аккаунта.','sessions':'Другие сеансы сайта завершены.',
                      'welcome':'Добро пожаловать!','reset':'Пароль изменён. Войди с новым паролем.','error':'Не удалось выполнить действие. Проверь введённые данные.',
                      'limit':'Слишком много попыток. Повтори позже.','login':'Войди в аккаунт, чтобы продолжить.',
                       'email_sent':'Проверь почту: если письмо было доставлено, подтверди адрес по ссылке.',
                       'email_verified':'Email подтверждён.',
                       'email_changed':'Адрес email изменён. Войди заново.',
                       'email_error':'Письмо отправить не удалось. Попробуй позже.',
                       'email_unavailable':'Отправка писем не настроена.',
                       'email_invalid':'Не удалось изменить email. Проверь данные или используй другой адрес.',
                       'email_password':'Не удалось подтвердить пароль сайта.'}
            message=statuses.get(qs.get('message',[''])[0],'')
            status=200
            if path=='/sso/authorize':
                if not sso.enabled():
                    return self.error_page(404,'НЕ НАЙДЕНО','Единый вход не настроен.')
                client=qs.get('client',[''])[0]
                state=qs.get('state',[''])[0]
                target=sso.authorization_path(client,state)
                if not target:
                    return self.error_page(400,'НЕКОРРЕКТНЫЙ ЗАПРОС','Недействительный запрос авторизации.')
                if not user:
                    return self.redirect('/login?'+urlencode({'next':target}),new_cookie)
                code=sso.issue_code(c,user['user_id'])
                callback=sso.CALLBACK+'?'+urlencode({'state':state,'code':code})
                return self.response(b'',303,'text/plain; charset=utf-8',new_cookie,{'Location':callback})
            if path=='/verify-email':
                token=qs.get('token',[''])[0]
                proof=email_verify.get(c,token)
                needs_login=bool(proof and proof['purpose']=='change' and
                                 (not user or user['user_id']!=proof['user_id']))
                title='Подтверждение email'
                body=v.email_confirmation_page(csrf,token,proof,needs_login)
                if not proof:status=400
            elif path=='/forgot':
                if qs.get('message',[''])[0]=='sent':
                    notice='Если адрес зарегистрирован и почта настроена, письмо с инструкцией будет отправлено.'
                elif qs.get('message',[''])[0]=='invalid':
                    notice='Ссылка недействительна или устарела. Запроси новую.'
                else:
                    notice=''
                title='Восстановление доступа'
                body=v.recovery_request_page(csrf,recovery.enabled(BASE_URL),notice)
            elif path=='/reset':
                token=qs.get('token',[''])[0]
                valid=recovery.exists(c,token)
                title='Новый пароль'
                body=v.recovery_reset_page(csrf,token,valid)
                if not valid:status=400
            elif path=='/':title='Главная';body=v.home(c,config)
            elif path=='/about':title='О проекте';body=v.about_page(config)
            elif path=='/play':title='Начать играть';body=v.play_page(config)
            elif path=='/servers':title='Серверы';body=v.servers_page(c)
            elif path=='/news':title='Новости';body=v.news_page(c)
            elif re.fullmatch('/news/[0-9]{1,9}',path):
                n=c.execute('SELECT * FROM news WHERE id=? AND published=1',(int(path.split('/')[-1]),)).fetchone()
                if n:title=n['title'];body=v.article_page(n)
                else:title='Страница не найдена';body=v.not_found();status=404
            elif path=='/donate':title='Игровой магазин';body=v.donate_page(config)
            elif path=='/rules':title='Правила сайта';body=v.rules_page()
            elif path=='/privacy':title='Конфиденциальность';body=v.privacy_page(config)
            elif path=='/contact':title='Поддержка';body=v.contact_page(user,csrf)
            elif path=='/login':
                ret=sso.login_return(qs.get('next',[''])[0])
                if user:return self.redirect(ret or '/account',new_cookie)
                title='Вход';body=v.auth_page('login',csrf,next_url=ret)
            elif path=='/register':
                ret=sso.login_return(qs.get('next',[''])[0])
                if user:return self.redirect(ret or '/account',new_cookie)
                title='Регистрация';body=v.auth_page('register',csrf,next_url=ret)
            elif path=='/account':
                if not user:return self.redirect('/login?message=login',new_cookie)
                title='Личный кабинет';body=v.account_page(c,user,csrf,recovery.enabled(BASE_URL))
                if sso.enabled():
                    forum_login=sso.CALLBACK.removesuffix('/sso/callback')+'/sso/login'
                    body+='<section class="section compact"><div class="shell"><div class="panel dashboard-panel"><h2>ФОРУМ OBSIDIAN RUSSIA</h2><p>Войти на форум можно через этот аккаунт сайта, без повторного ввода пароля.</p><a class="btn btn-primary" href="'+v.E(forum_login)+'">Войти на форум</a></div></div></section>'
            elif path=='/admin':
                if not user or user['role']!='admin':return self.redirect('/login?message=login' if not user else '/account',new_cookie)
                tab=qs.get('tab',['overview'])[0]
                if tab not in ('overview','news','servers','tickets','settings'):tab='overview'
                title='Администрирование';body=v.admin_page(c,tab,csrf,message)
                if tab=='news':
                    try:edit=int(qs.get('edit',['0'])[0])
                    except ValueError:edit=0
                    if edit:
                        n=c.execute('SELECT * FROM news WHERE id=?',(edit,)).fetchone()
                        if n:body=body.replace(v.admin_news_form(c,csrf),v.admin_news_form_for_item(n,csrf),1)
                message=''
            else:title='Страница не найдена';body=v.not_found();status=404
            self.response(v.layout(title,body,path,user,config,csrf,message),status,cookie=new_cookie)

    def do_POST(self):
        self._db_connection=None
        try:self.handle_post()
        except (BrokenPipeError,ConnectionResetError):pass
        except BadRequest as ex:self.error_page(400,'ОШИБКА ФОРМЫ',str(ex))
        except sqlite3.IntegrityError:
            logging.info('unique field conflict')
            self.redirect('/register?message=error')
        except Exception:
            logging.exception('POST failed')
            try:self.error_page(500,'ОШИБКА СЕРВЕРА','Операция не выполнена.')
            except Exception:pass

    def handle_post(self):
        path=urlsplit(self.path).path
        f=self.form()
        if path=='/sso/session-version':
            if not allowed(self.client_ip(),'sso_version',120,60):
                return self.response('{"error":"unauthorized"}',401,'application/json; charset=utf-8')
            with connect() as c:
                version=sso.identity_version(c,f.get('client_id',''),f.get('client_secret',''),f.get('sub',''))
                if version is None:
                    return self.response('{"error":"unauthorized"}',401,'application/json; charset=utf-8')
                return self.response(json.dumps({'auth_version':version}),200,'application/json; charset=utf-8')
        if path=='/sso/token':
            if not allowed(self.client_ip(),'sso_token',50,60):
                return self.response('{"error":"unauthorized"}',401,'application/json; charset=utf-8')
            with connect() as c:
                identity=sso.redeem_code(c,f.get('client_id',''),f.get('client_secret',''),f.get('code',''))
                if identity:
                    c.commit()
                    return self.response(json.dumps(identity,ensure_ascii=False),200,'application/json; charset=utf-8')
                return self.response('{"error":"unauthorized"}',401,'application/json; charset=utf-8')
        with connect() as c:
            self._db_connection=c
            session,_=self.session_from_request(c)
            if not session or not hmac.compare_digest(f.get('csrf',''),session['csrf']):
                raise BadRequest('Срок действия формы истёк. Обнови страницу и попробуй снова.')
            user=session if session['user_id'] else None
            client=self.client_ip()
            if path=='/verify-email':
                proof=email_verify.get(c,f.get('token',''))
                previous=(c.execute('SELECT email,email_verified_at FROM users WHERE id=?',
                                    (proof['user_id'],)).fetchone()
                          if proof and proof['purpose']=='change' else None)
                result=email_verify.confirm(c,f.get('token',''),
                            user['user_id'] if user else None)
                if result=='changed':
                    security_events.record(c,proof['user_id'],'email_changed')
                    c.commit()  # Persist the change before best-effort notification.
                    if previous and previous['email_verified_at']:
                        security_events.notify_address(previous['email'],'email_changed')
                    return self.redirect('/login?message=email_changed','')
                if result=='verified':
                    if proof:
                        security_events.record(c,proof['user_id'],'email_verified')
                    return self.redirect('/account?message=email_verified' if user else '/login?message=email_verified')
                if result=='login_required':
                    return self.redirect('/login?message=login')
                return self.redirect('/account?message=email_invalid' if user else '/login?message=error')
            if path=='/forgot':
                if not recovery.enabled(BASE_URL):
                    return self.error_page(503,'ВОССТАНОВЛЕНИЕ НЕДОСТУПНО','Почта для восстановления не настроена.')
                if not allowed(client,'forgot',5,3600):
                    return self.redirect('/forgot?message=sent')
                email=f.get('email','').strip().lower()
                if len(email)>120 or not recovery.EMAIL_PATTERN.fullmatch(email):
                    return self.redirect('/forgot?message=sent')
                email_key=hashlib.sha256(email.encode('utf-8')).hexdigest()
                if not allowed(email_key,'forgot-email',3,3600):
                    return self.redirect('/forgot?message=sent')
                target=c.execute('SELECT id,email FROM users WHERE email=? AND email_verified_at IS NOT NULL',(email,)).fetchone()
                if target:
                    token=recovery.issue(c,target['id'])
                    c.commit()  # Token must exist before mail delivery starts.
                    try:
                        recovery.send_email(target['email'],token,BASE_URL)
                    except Exception:
                        # Don't reveal account existence or mail delivery status.
                        logging.warning('Password recovery delivery failed; check SMTP configuration')
                        recovery.cancel(c,token)
                        c.commit()
                return self.redirect('/forgot?message=sent')
            if path=='/reset':
                if not allowed(client,'reset',12,3600):
                    return self.error_page(429,'СЛИШКОМ МНОГО ПОПЫТОК','Повтори позднее.')
                pw=f.get('password','')
                confirm=f.get('confirm','')
                token=f.get('token','')
                if pw!=confirm or not 10<=len(pw)<=128:
                    return self.error_page(400,'ПРОВЕРЬ ПАРОЛЬ','Пароль должен содержать 10–128 символов, оба поля должны совпадать.')
                recovered_user_id=recovery.redeem(c,token,pw)
                if not recovered_user_id:
                    return self.redirect('/forgot?message=invalid')
                security_events.record(c,recovered_user_id,'password_reset')
                c.commit()
                security_events.notify_verified(c,recovered_user_id,'password_reset')
                return self.redirect('/login?message=reset','')
            if path=='/login':
                if not allowed(client,'login',12,900):return self.redirect('/login?message=limit')
                ident=f.get('identity','').strip(); pw=f.get('password','')
                if len(ident)>120 or len(pw)>128:return self.redirect('/login?message=error')
                u=c.execute('SELECT * FROM users WHERE username=? OR email=?',(ident,ident)).fetchone()
                if not u or not check_password(pw,u['password_hash']):
                    # Consistent work for unknown usernames, within reasonable limits.
                    if not u:hashlib.pbkdf2_hmac('sha256',b'dummy',b'\x00'*16,260000)
                    return self.redirect('/login?message=error')
                c.execute('DELETE FROM sessions WHERE token_hash=?',(session['token_hash'],))
                token=new_token(c,u['id'])
                return self.redirect(sso.login_return(f.get('next','')) or '/account?message=welcome',token)
            if path=='/register':
                if not allowed(client,'register',5,3600):return self.redirect('/register?message=limit')
                uname=f.get('username','').strip();email=f.get('email','').lower().strip();pw=f.get('password','');pw2=f.get('password2','')
                if not (3<=len(uname)<=24 and re.fullmatch(r'[A-Za-zА-Яа-яЁё0-9_]+',uname)
                    and 5<=len(email)<=120 and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)
                    and 10<=len(pw)<=128 and pw==pw2):return self.redirect('/register?message=error')
                if c.execute('SELECT 1 FROM users WHERE username=? OR email=?',(uname,email)).fetchone():return self.redirect('/register?message=error')
                cur=c.execute('INSERT INTO users(username,email,password_hash,role,created_at) VALUES(?,?,?,?,?)',(uname,email,hash_password(pw),'user',now()))
                c.execute('DELETE FROM sessions WHERE token_hash=?',(session['token_hash'],))
                token=new_token(c,cur.lastrowid)
                notice='welcome'
                if recovery.enabled(BASE_URL):
                    email_token=email_verify.issue(c,cur.lastrowid,email,'verify')
                    c.commit()
                    try:
                        email_verify.send_email(email,email_token,BASE_URL,'verify')
                        notice='email_sent'
                    except Exception:
                        logging.warning('Registration verification delivery failed; check SMTP configuration')
                        email_verify.cancel(c,email_token)
                        c.commit()
                        notice='email_error'
                return self.redirect(sso.login_return(f.get('next','')) or '/account?message='+notice,token)
            if path=='/logout':
                c.execute('DELETE FROM sessions WHERE token_hash=?',(session['token_hash'],))
                return self.redirect('/?message=bye','')
            if not user:return self.redirect('/login?message=login')
            if path=='/account/email/resend':
                if not recovery.enabled(BASE_URL):
                    return self.redirect('/account?message=email_unavailable')
                if user['email_verified_at']:
                    return self.redirect('/account')
                if not allowed(client,'verify-mail',6,3600) or not allowed(str(user['user_id']),'verify-user',3,3600):
                    return self.redirect('/account?message=limit')
                token=email_verify.issue(c,user['user_id'],user['email'],'verify')
                c.commit()
                try:
                    email_verify.send_email(user['email'],token,BASE_URL,'verify')
                except Exception:
                    logging.warning('Email verification delivery failed; check SMTP configuration')
                    email_verify.cancel(c,token)
                    c.commit()
                    return self.redirect('/account?message=email_error')
                security_events.record(c,user['user_id'],'email_change_requested')
                c.commit()
                security_events.notify_verified(c,user['user_id'],'email_change_requested')
                return self.redirect('/account?message=email_sent')
            if path=='/account/email/change':
                if not recovery.enabled(BASE_URL):
                    return self.redirect('/account?message=email_unavailable')
                if not allowed(client,'change-mail',6,3600) or not allowed(str(user['user_id']),'change-user',3,3600):
                    return self.redirect('/account?message=limit')
                address=f.get('email','').strip().lower()
                password=f.get('password','')
                if not email_verify.valid_email(address) or address.casefold()==user['email'].casefold():
                    return self.redirect('/account?message=email_invalid')
                row=c.execute('SELECT password_hash FROM users WHERE id=?',(user['user_id'],)).fetchone()
                if len(password)>128 or not row or not check_password(password,row['password_hash']):
                    return self.redirect('/account?message=email_password')
                if c.execute('SELECT 1 FROM users WHERE email=?',(address,)).fetchone():
                    return self.redirect('/account?message=email_invalid')
                token=email_verify.issue(c,user['user_id'],address,'change')
                c.commit()
                try:
                    email_verify.send_email(address,token,BASE_URL,'change')
                except Exception:
                    logging.warning('Email change delivery failed; check SMTP configuration')
                    email_verify.cancel(c,token)
                    c.commit()
                    return self.redirect('/account?message=email_error')
                return self.redirect('/account?message=email_sent')
            if path=='/account/sessions/close-others':
                c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(user['user_id'],session['token_hash']))
                security_events.record(c,user['user_id'],'sessions_closed')
                return self.redirect('/account?message=sessions')
            if path=='/account/sessions/logout-all':
                # Invalidate linked forum sessions as well as website sessions.
                c.execute('UPDATE users SET auth_version=auth_version+1 WHERE id=?',(user['user_id'],))
                c.execute('DELETE FROM sso_codes WHERE user_id=?',(user['user_id'],))
                c.execute('DELETE FROM sessions WHERE user_id=?',(user['user_id'],))
                security_events.record(c,user['user_id'],'sessions_closed_all')
                return self.redirect('/?message=bye','')
            if path=='/account/password':
                if not allowed(client,'password',8,900):return self.redirect('/account?message=limit')
                pw=f.get('old_password','');new_pw=f.get('new_password','')
                row=c.execute('SELECT password_hash FROM users WHERE id=?',(user['user_id'],)).fetchone()
                if not row or not check_password(pw,row['password_hash']) or not 10<=len(new_pw)<=128:
                    return self.redirect('/account?message=error')
                c.execute('UPDATE users SET password_hash=?,auth_version=auth_version+1 WHERE id=?',(hash_password(new_pw),user['user_id']))
                c.execute('DELETE FROM sso_codes WHERE user_id=?',(user['user_id'],))
                c.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(user['user_id'],session['token_hash']))
                security_events.record(c,user['user_id'],'password_changed')
                c.commit()
                security_events.notify_verified(c,user['user_id'],'password_changed')
                return self.redirect('/account?message=password')
            if path=='/contact':
                if not allowed(client,'ticket',5,3600):return self.redirect('/contact?message=limit')
                sub=f.get('subject','').strip(); msg=f.get('message','').strip()
                if not (3<=len(sub)<=100 and 10<=len(msg)<=3000):return self.redirect('/contact?message=error')
                c.execute('INSERT INTO tickets(user_id,subject,message,status,created_at) VALUES(?,?,?,"open",?)',(user['user_id'],sub,msg,now()))
                return self.redirect('/account?message=ticket')
            if user['role']!='admin':return self.error_page(403,'НЕДОСТАТОЧНО ПРАВ','Только администрация может изменять сайт.')
            if path=='/admin/news/save':
                title=f.get('title','').strip();excerpt=f.get('excerpt','').strip();body=f.get('body','').strip();cat=f.get('category','Новости')
                if not (3<=len(title)<=130 and 3<=len(excerpt)<=250 and 10<=len(body)<=20000 and cat in ('Новости','Разработка','Обновление','События','Важно')):
                    return self.redirect('/admin?tab=news&message=error')
                pub=1 if f.get('published')=='1' else 0
                try: id=int(f.get('id') or 0)
                except ValueError:id=0
                if id:
                    c.execute('UPDATE news SET title=?,excerpt=?,body=?,category=?,published=?,updated_at=? WHERE id=?',(
                        title,excerpt,body,cat,pub,now(),id))
                else:
                    c.execute('INSERT INTO news(title,excerpt,body,category,published,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(
                        title,excerpt,body,cat,pub,now(),now()))
                return self.redirect('/admin?tab=news&message=saved')
            if path=='/admin/news/delete':
                try:id=int(f.get('id',''))
                except ValueError:raise BadRequest('Неверный ID')
                c.execute('DELETE FROM news WHERE id=?',(id,))
                return self.redirect('/admin?tab=news&message=deleted')
            if path=='/admin/servers/add':
                name=f.get('name','').strip();description=f.get('description','').strip()
                if not (3<=len(name)<=70 and len(description)<=200):return self.redirect('/admin?tab=servers&message=error')
                c.execute('INSERT INTO servers(name,description,status,updated_at) VALUES(?,?,?,?)',(name,description,'soon',now()))
                return self.redirect('/admin?tab=servers&message=created')
            if path=='/admin/servers/save':
                try:id=int(f.get('id','')); on=int(f.get('online','0'));maxp=int(f.get('capacity','0'))
                except ValueError:return self.redirect('/admin?tab=servers&message=error')
                name=f.get('name','').strip();addr=f.get('address','').strip();description=f.get('description','').strip();status=f.get('status','soon')
                if not (id>0 and 3<=len(name)<=70 and len(addr)<=140 and len(description)<=200 and status in ('soon','online','offline') and 0<=on<=maxp<=100000):return self.redirect('/admin?tab=servers&message=error')
                c.execute('UPDATE servers SET name=?,address=?,description=?,online=?,capacity=?,status=?,updated_at=? WHERE id=?',(
                    name,addr,description,on,maxp,status,now(),id))
                return self.redirect('/admin?tab=servers&message=saved')
            if path=='/admin/settings':
                keys=['vk','telegram','forum','android_download','windows_download','donation_url','support_email','site_notice']
                for key in keys:
                    value=f.get(key,'').strip()
                    if key=='site_notice':
                        if len(value)>400:return self.redirect('/admin?tab=settings&message=error')
                    elif key=='support_email':
                        if len(value)>120 or (value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value)):
                            return self.redirect('/admin?tab=settings&message=error')
                    elif not valid_url(value):
                        return self.redirect('/admin?tab=settings&message=error')
                for key in keys:c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,f.get(key,'').strip()))
                return self.redirect('/admin?tab=settings&message=saved')
            if path=='/admin/tickets/status':
                status=f.get('status');id=f.get('id')
                if status not in ('open','closed') or not id or not id.isdigit():raise BadRequest('Неверный статус')
                c.execute('UPDATE tickets SET status=? WHERE id=?',(status,int(id)))
                return self.redirect('/admin?tab=tickets&message=saved')
            self.error_page(404,'НЕ НАЙДЕНО','Неизвестный обработчик формы.')

def main():
    # Preserve readable terminal output on Windows and avoid cp1252 startup failures.
    if sys.stdout is not None and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='backslashreplace')
    logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(message)s')
    init_db()
    with connect() as c:
        c.execute('DELETE FROM sessions WHERE expires_at<?',(now(),))
    server=ThreadingHTTPServer((HOST,PORT),Handler)
    print(f'OBSIDIAN RUSSIA открыт: http://{HOST}:{PORT}')
    print('Администратора можно создать через: python manage.py')
    print('Остановка: Ctrl+C')
    try:server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
