"""OBSIDIAN RUSSIA WIKI — independent knowledge base, Python 3.12+ stdlib.
Local: python app.py. Admin: python manage.py admin.
Before exposing publicly: HTTPS reverse proxy, secure cookies, rate limiting upstream,
backups, legal privacy notice, authenticated editorial workflow.
"""
import hashlib, hmac, json, logging, mimetypes, os, re, secrets, sqlite3, threading, time
from collections import defaultdict, deque
from email.parser import BytesParser
from email.policy import default
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, quote

import db
import views as v

ROOT=Path(__file__).resolve().parent
STATIC=(ROOT/'static').resolve()
HOST=os.getenv('OBWIKI_BIND','127.0.0.1')
PORT=int(os.getenv('OBWIKI_PORT','8100'))
BASE_URL=os.getenv('OBWIKI_BASE_URL',f'http://localhost:{PORT}').rstrip('/')
SECURE=os.getenv('OBWIKI_SECURE_COOKIE','0')=='1'
RATE=defaultdict(deque)
LOCK=threading.Lock()
MAX_FORM=450_000
MAX_UPLOAD=3*1024*1024

class BadRequest(Exception):pass
class NoAccess(Exception):pass

def throttle(ip,scope,limit=12,window=900):
    stamp=time.monotonic()
    with LOCK:
        q=RATE[(ip,scope)]
        while q and q[0]<stamp-window:q.popleft()
        if len(q)>=limit:return False
        q.append(stamp)
        if len(RATE)>20000:
            for k in list(RATE)[:5000]:
                if not RATE[k] or RATE[k][-1]<stamp-window:RATE.pop(k,None)
        return True

def integer(x,default=1,hi=999):
    try:return max(1,min(hi,int(x)))
    except (ValueError,TypeError):return default

def sql_search(c,q,category,page):
    cond=["a.status='published'"]
    args=[]
    if category:
        cond.append('cat.slug=?');args.append(category)
    tokens=[t for t in re.split(r'\s+',q.casefold()) if t][:6]
    for t in tokens:
        pattern='%'+t.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        cond.append("(fold(a.title) LIKE ? ESCAPE '\\' OR fold(a.summary) LIKE ? ESCAPE '\\' OR fold(a.content) LIKE ? ESCAPE '\\' OR fold(cat.title) LIKE ? ESCAPE '\\')")
        args.extend([pattern]*4)
    where=' AND '.join(cond)
    from_clause='FROM articles a JOIN categories cat ON a.category_id=cat.id'
    count=c.execute('SELECT COUNT(*) '+from_clause+' WHERE '+where,args).fetchone()[0]
    rows=c.execute('SELECT a.*,cat.title category_title,cat.slug category_slug,cat.icon category_icon '+from_clause+' WHERE '+where+' ORDER BY a.featured DESC,a.updated_at DESC,a.id DESC LIMIT 15 OFFSET ?',args+[(page-1)*15]).fetchall()
    return rows,count

def article_join(c,where='',args=(),suffix=''):
    return c.execute('SELECT a.*,cat.title category_title,cat.slug category_slug,cat.icon category_icon FROM articles a JOIN categories cat ON cat.id=a.category_id '+where+' '+suffix,args).fetchall()

def categories(c):
    return c.execute('''SELECT cat.*, (SELECT count(*) FROM articles a WHERE a.category_id=cat.id AND a.status='published') article_count
      FROM categories cat ORDER BY cat.sort_order,cat.id''').fetchall()

def get_cookie(headers,name):
    c=SimpleCookie()
    try:c.load(headers.get('Cookie',''))
    except Exception:return ''
    return c[name].value if name in c else ''

def security_headers(handler,ctype,length,cache=False):
    handler.send_header('Content-Type',ctype)
    handler.send_header('Content-Length',str(length))
    handler.send_header('X-Content-Type-Options','nosniff')
    handler.send_header('X-Frame-Options','DENY')
    handler.send_header('Referrer-Policy','strict-origin-when-cross-origin')
    handler.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
    handler.send_header('Cross-Origin-Resource-Policy','same-origin')
    handler.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; connect-src 'self'")
    handler.send_header('Cache-Control','public, max-age=3600' if cache else 'no-store')
    if SECURE:handler.send_header('Strict-Transport-Security','max-age=31536000; includeSubDomains')

def static_path(path):
    name=path.removeprefix('/static/')
    f=(STATIC/name).resolve()
    if not f.is_relative_to(STATIC) or not f.is_file():return None
    if f.suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.css','.js','.ico','.svg'):return None
    return f

class Handler(BaseHTTPRequestHandler):
    server_version='ObsidianWiki/1.0'
    sys_version=''
    def log_message(self,fmt,*args):logging.info('%s %s',self.client_address[0],fmt%args)
    def respond(self,body='',status=200,ctype='text/html; charset=utf-8',cookies=(),cache=False,headers=None):
        if isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status)
        security_headers(self,ctype,len(body),cache)
        for cookie in cookies:self.send_header('Set-Cookie',cookie)
        for k,val in (headers or {}).items():self.send_header(k,val)
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)
    def redirect(self,url,cookies=()):
        if not url.startswith('/') or url.startswith('//') or '\\' in url or '\n' in url or '\r' in url:url='/'
        self.respond('',303,'text/plain; charset=utf-8',cookies,headers={'Location':url})
    def cookie(self,name,token,clear=False):
        secure='; Secure' if SECURE else ''
        return f'{name}={token if not clear else ""}; Path=/; HttpOnly; SameSite=Lax; Max-Age={"0" if clear else "604800"}{secure}'
    def read_form(self,limit=MAX_FORM):
        if not self.headers.get('Content-Type','').lower().startswith('application/x-www-form-urlencoded'):raise BadRequest('Ожидалась HTML-форма.')
        try:
            n=int(self.headers.get('Content-Length','-1'))
            if n<0 or n>limit:raise BadRequest('Слишком большой запрос.')
            data=self.rfile.read(n)
            if len(data)!=n:raise BadRequest('Неполные данные.')
            params=parse_qs(data.decode('utf-8','strict'),max_num_fields=30,keep_blank_values=True)
            return {k:v[0] if v else '' for k,v in params.items()}
        except (UnicodeError,ValueError) as e:raise BadRequest('Неверный формат формы.') from e
    def read_upload(self):
        content_type=self.headers.get('Content-Type','')
        if not content_type.lower().startswith('multipart/form-data;'):raise BadRequest('Ожидался файл изображения.')
        try:size=int(self.headers.get('Content-Length','0'))
        except ValueError:raise BadRequest('Некорректный размер файла.')
        if size<=0 or size>MAX_UPLOAD+100_000:raise BadRequest('Файл превышает 3 МБ.')
        raw=self.rfile.read(size)
        if len(raw)!=size:raise BadRequest('Не удалось прочитать файл.')
        message=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
        if not message.is_multipart():raise BadRequest('Неверный multipart-запрос.')
        parts=list(message.iter_parts())
        if len(parts)>3:raise BadRequest('Лишние поля файла.')
        fields={p.get_param('name',header='content-disposition'):p for p in parts}
        token=fields.get('csrf')
        pic=fields.get('image')
        if not token or not pic:raise BadRequest('Нет изображения или защитного токена.')
        key=token.get_content().strip()
        data=pic.get_payload(decode=True)
        if not data or len(data)>MAX_UPLOAD:raise BadRequest('Неверный размер изображения.')
        ext=''
        if data[:8]==b'\x89PNG\r\n\x1a\n' and data[12:16]==b'IHDR':ext='.png'
        elif data[:3]==b'\xff\xd8\xff' and data[-2:]==b'\xff\xd9':ext='.jpg'
        elif len(data)>12 and data[:4]==b'RIFF' and data[8:12]==b'WEBP':ext='.webp'
        if not ext:raise BadRequest('Разрешены только настоящие JPEG, PNG или WebP.')
        # Bound dimensions when the headers expose them; browser handles further image validation.
        if ext=='.png':
            width,height=int.from_bytes(data[16:20],'big'),int.from_bytes(data[20:24],'big')
            if not (1<=width<=10000 and 1<=height<=10000):raise BadRequest('Некорректные размеры изображения.')
        original=pic.get_filename() or 'image'+ext
        return key,data,ext,original[:100]
    def user(self,c):
        return db.session_for(c,get_cookie(self.headers,'obwiki_session'))
    def required_user(self,c,form=None,role=None):
        u=self.user(c)
        if not u:raise NoAccess('Войдите в панель управления.')
        if role and u['role']!=role:raise NoAccess('Недостаточно прав.')
        if form is not None:
            token=form.get('csrf','')
            if not hmac.compare_digest(token,u['csrf']):raise BadRequest('Неверный защитный токен формы.')
        return u
    def do_HEAD(self):self.do_GET()
    def do_GET(self):
        c=None
        try:
            path=urlsplit(self.path).path
            if path.startswith('/static/'):
                f=static_path(path)
                if not f:return self.respond('Не найдено',404,'text/plain; charset=utf-8')
                mime,_=mimetypes.guess_type(f.name)
                if f.suffix=='.js':mime='application/javascript'
                return self.respond(f.read_bytes(),200,(mime or 'application/octet-stream'),cache=True)
            c=db.connect();c.create_function('fold',1,lambda s:(s or '').casefold(),deterministic=True)
            u=self.user(c);cats=categories(c)
            qs=parse_qs(urlsplit(self.path).query)
            param=lambda k,default='':qs.get(k,[default])[0][:200]
            if path=='/':
                featured=article_join(c,"WHERE a.status='published' AND a.featured=1",(), 'ORDER BY a.updated_at DESC,a.id LIMIT 6')
                latest=article_join(c,"WHERE a.status='published'",(), 'ORDER BY a.updated_at DESC,a.id DESC LIMIT 5')
                count=c.execute("SELECT count(*) FROM articles WHERE status='published'").fetchone()[0]
                return self.respond(v.homepage(cats,featured,latest,count,u))
            if path=='/categories':return self.respond(v.category_index(cats,u))
            if path.startswith('/category/'):
                slug=path.removeprefix('/category/')
                cat=c.execute('SELECT * FROM categories WHERE slug=?',(slug,)).fetchone()
                if not cat:return self.respond(v.notfound(cats,u),404)
                articles=article_join(c,"WHERE a.status='published' AND cat.slug=?",(slug,), 'ORDER BY a.featured DESC,a.title')
                return self.respond(v.category_page(cat,articles,cats,u))
            if path.startswith('/article/'):
                slug=path.removeprefix('/article/')
                rows=article_join(c,'WHERE a.slug=? AND (a.status=\'published\' OR ?=1)',(slug,1 if u else 0))
                if not rows:return self.respond(v.notfound(cats,u),404)
                a=rows[0]
                if a['status']=='published':
                    c.execute('UPDATE articles SET views=views+1 WHERE id=?',(a['id'],));c.commit()
                    a=article_join(c,'WHERE a.id=?',(a['id'],))[0]
                related=article_join(c,'WHERE a.category_id=? AND a.id<>? AND a.status=\'published\'',(a['category_id'],a['id']),'ORDER BY a.featured DESC,a.updated_at DESC LIMIT 3')
                return self.respond(v.article_page(a,cats,related,u))
            if path in ('/search','/articles'):
                q=param('q') if path=='/search' else ''
                category=param('category');page=integer(param('page','1'),hi=9999)
                results,total=sql_search(c,q,category,page)
                body=v.search_page(q,results,cats,total,page,category,'Поиск' if path=='/search' else 'Все статьи')
                return self.respond(v.base('Поиск' if q else 'Каталог статей',body,cats,u,'articles'))
            if path=='/catalog':
                counts={r['kind']:r['n'] for r in c.execute("SELECT kind,COUNT(*) n FROM catalog_items WHERE status='published' GROUP BY kind")}
                return self.respond(v.catalog_index(db.CATALOG_TYPES,counts,cats,u))
            if path.startswith('/catalog/item/'):
                slug=path.removeprefix('/catalog/item/')
                a=c.execute("SELECT * FROM catalog_items WHERE slug=? AND (status='published' OR ?=1)",(slug,1 if u else 0)).fetchone()
                if not a:return self.respond(v.notfound(cats,u),404)
                typ=next((t for t in db.CATALOG_TYPES if t[0]==a['kind']),None)
                if not typ:return self.respond(v.notfound(cats,u),404)
                return self.respond(v.catalog_item(a,typ[1],typ[3],cats,u))
            if path.startswith('/catalog/'):
                kind=path.removeprefix('/catalog/')
                typ=next((t for t in db.CATALOG_TYPES if t[0]==kind),None)
                if not typ:return self.respond(v.notfound(cats,u),404)
                q=param('q')[:100];tier=param('tier')[:80]
                terms=['kind=?',"status='published'"];values=[kind]
                if tier:terms.append('tier=?');values.append(tier)
                if q:
                    phrase='%'+q.casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                    terms.append("(fold(title) LIKE ? ESCAPE '\\' OR fold(summary) LIKE ? ESCAPE '\\' OR fold(parameters) LIKE ? ESCAPE '\\')")
                    values.extend([phrase]*3)
                items=c.execute('SELECT * FROM catalog_items WHERE '+' AND '.join(terms)+' ORDER BY title LIMIT 150',values).fetchall()
                tiers=[r['tier'] for r in c.execute("SELECT DISTINCT tier FROM catalog_items WHERE kind=? AND status='published' AND tier<>'' ORDER BY tier",(kind,))]
                return self.respond(v.catalog_kind(kind,typ[1],typ[2],typ[3],items,tiers,q,tier,cats,u))
            if path=='/about':return self.respond(v.about(cats,u))
            if path=='/privacy':return self.respond(v.privacy(cats,u))
            if path=='/login':
                if u:return self.redirect('/admin')
                guest=secrets.token_urlsafe(32)
                return self.respond(v.login(cats,guest),cookies=[self.cookie('obwiki_guest',guest)])
            if path=='/admin':
                if not u:return self.redirect('/login')
                counts=[('Опубликовано',c.execute("SELECT count(*) FROM articles WHERE status='published'").fetchone()[0]),('Черновики',c.execute("SELECT count(*) FROM articles WHERE status='draft'").fetchone()[0]),('Категории',len(cats)),('Просмотры',c.execute('SELECT COALESCE(sum(views),0) FROM articles').fetchone()[0])]
                recent=c.execute('SELECT * FROM articles ORDER BY updated_at DESC,id DESC LIMIT 9').fetchall()
                return self.respond(v.admin_dashboard(counts,recent,u,cats,param('info')))
            if path=='/admin/articles':
                if not u:return self.redirect('/login')
                rows=article_join(c,'',(),'ORDER BY a.updated_at DESC,a.id DESC LIMIT 300')
                return self.respond(v.admin_articles(rows,u,cats,param('info')))
            if path in ('/admin/article/new',) or re.fullmatch(r'/admin/article/\d+',path):
                if not u:return self.redirect('/login')
                a=None if path.endswith('/new') else c.execute('SELECT * FROM articles WHERE id=?',(int(path.split('/')[-1]),)).fetchone()
                if not a and not path.endswith('/new'):return self.respond(v.notfound(cats,u),404)
                rev=[] if a is None else c.execute('SELECT r.*,u.username FROM revisions r LEFT JOIN users u ON r.user_id=u.id WHERE r.article_id=? ORDER BY r.id DESC LIMIT 15',(a['id'],)).fetchall()
                return self.respond(v.admin_article_form(a,cats,u,rev,param('info')))
            if path=='/admin/catalog':
                if not u:return self.redirect('/login')
                entries=c.execute('SELECT * FROM catalog_items ORDER BY updated_at DESC,id DESC LIMIT 300').fetchall()
                return self.respond(v.admin_catalog(entries,u,cats,param('info')))
            if path=='/admin/catalog/new' or re.fullmatch(r'/admin/catalog/item/\d+',path):
                if not u:return self.redirect('/login')
                a=None if path.endswith('/new') else c.execute('SELECT * FROM catalog_items WHERE id=?',(int(path.split('/')[-1]),)).fetchone()
                if a is None and not path.endswith('/new'):return self.respond(v.notfound(cats,u),404)
                return self.respond(v.admin_catalog_editor(a,db.CATALOG_TYPES,u,cats,param('info')))
            if path=='/admin/categories':
                if not u:return self.redirect('/login')
                return self.respond(v.admin_categories(cats,u,param('info')))
            if path=='/admin/media':
                if not u:return self.redirect('/login')
                rows=c.execute('SELECT * FROM media ORDER BY id DESC LIMIT 100').fetchall()
                return self.respond(v.admin_media(rows,u,cats,param('info')))
            if path=='/admin/users':
                if not u:return self.redirect('/login')
                if u['role']!='admin':raise NoAccess('Только для администратора.')
                users=c.execute('SELECT id,username,role,created_at FROM users ORDER BY id').fetchall()
                return self.respond(v.admin_users(users,u,cats,param('info')))
            if path=='/admin/audit':
                if not u:return self.redirect('/login')
                if u['role']!='admin':raise NoAccess('Только для администратора.')
                logs=c.execute('SELECT l.*,u.username FROM audit l LEFT JOIN users u ON l.actor=u.id ORDER BY l.id DESC LIMIT 100').fetchall()
                return self.respond(v.admin_audit(logs,u,cats))
            if path=='/api/stats':
                stat={'articles':c.execute("SELECT count(*) FROM articles WHERE status='published'").fetchone()[0], 'categories':len(cats),'brand':'OBSIDIAN RUSSIA','wiki_version':'1.0.0'}
                return self.respond(json.dumps(stat,ensure_ascii=False),200,'application/json; charset=utf-8')
            if path=='/api/search':
                q=param('q')[:80]
                if len(q)<2:return self.respond('[]',200,'application/json; charset=utf-8')
                res,_=sql_search(c,q,'',1)
                payload=[{'title':a['title'],'category':a['category_title'],'slug':a['slug'],'icon':a['category_icon']} for a in res[:7]]
                return self.respond(json.dumps(payload,ensure_ascii=False),200,'application/json; charset=utf-8')
            if path=='/robots.txt':return self.respond('User-agent: *\nDisallow: /admin\nDisallow: /login\nSitemap: '+BASE_URL+'/sitemap.xml\n',200,'text/plain; charset=utf-8')
            if path=='/sitemap.xml':
                pages=['/','/categories','/articles','/about']+[f'/category/{a["slug"]}' for a in cats]+[f'/article/{r["slug"]}' for r in c.execute("SELECT slug FROM articles WHERE status='published'")]+['/catalog']+[f'/catalog/{t[0]}' for t in db.CATALOG_TYPES]+[f'/catalog/item/{r["slug"]}' for r in c.execute("SELECT slug FROM catalog_items WHERE status='published'")]
                xml='<?xml version="1.0" encoding="utf-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+v.E(BASE_URL+p)+'</loc></url>' for p in pages)+'</urlset>'
                return self.respond(xml,200,'application/xml; charset=utf-8')
            return self.respond(v.notfound(cats,u),404)
        except NoAccess as e:self.respond(v.notfound(categories(c) if c else [],None,403,str(e)),403)
        except BadRequest as e:self.respond(v.notfound(categories(c) if c else [],None,400,str(e)),400)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            logging.exception('GET %s',self.path)
            try:self.respond('Внутренняя ошибка сервера',500,'text/plain; charset=utf-8')
            except Exception:pass
        finally:
            if c:c.close()
    def do_POST(self):
        c=None
        try:
            path=urlsplit(self.path).path
            c=db.connect()
            # For upload, validate CSRF before touching files, using parser with a bounded Content-Length.
            if path=='/admin/upload':
                u=self.required_user(c)
                token,data,ext,name=self.read_upload()
                if not hmac.compare_digest(token,u['csrf']):raise BadRequest('Неверный защитный токен.')
                folder=STATIC/'uploads';folder.mkdir(exist_ok=True)
                filename=secrets.token_hex(16)+ext
                target=folder/filename
                with open(target,'xb') as f:f.write(data)
                pathimg='/static/uploads/'+filename
                c.execute('INSERT INTO media(path,name,uploaded_by,created_at) VALUES(?,?,?,?)',(pathimg,name,u['id'],db.now()))
                db.audit(c,u['id'],'upload',pathimg)
                c.commit();return self.redirect('/admin/media?info='+quote('Изображение загружено'))
            form=self.read_form()
            if path=='/login':
                guest=get_cookie(self.headers,'obwiki_guest')
                if not guest or not hmac.compare_digest(guest,form.get('csrf','')):raise BadRequest('Сессия формы истекла. Обновите страницу.')
                if not throttle(self.client_address[0],'login',7,900):raise BadRequest('Слишком много попыток входа. Попробуйте позже.')
                username=form.get('username','')[:50]
                password=form.get('password','')[:1000]
                user=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
                if not user or not db.verify_password(password,user['pass_hash']):
                    guest=secrets.token_urlsafe(32)
                    return self.respond(v.login(categories(c),guest,'Неверный логин или пароль.'),401,cookies=[self.cookie('obwiki_guest',guest)])
                token=db.create_session(c,user['id'])
                db.audit(c,user['id'],'login',username);c.commit()
                return self.redirect('/admin',cookies=[self.cookie('obwiki_session',token),self.cookie('obwiki_guest','',True)])
            u=self.required_user(c,form)
            if path=='/logout':
                c.execute('DELETE FROM sessions WHERE token_hash=?',(u['token_hash'],));c.commit()
                return self.redirect('/',cookies=[self.cookie('obwiki_session','',True)])
            if path=='/admin/article/new' or re.fullmatch(r'/admin/article/\d+',path):
                is_new=path.endswith('/new')
                a=None if is_new else c.execute('SELECT * FROM articles WHERE id=?',(int(path.split('/')[-1]),)).fetchone()
                if not is_new and not a:raise BadRequest('Статья не найдена.')
                title=form.get('title','').strip();slug=form.get('slug','').strip();summary=form.get('summary','').strip()
                content=form.get('content','').strip();difficulty=form.get('difficulty','Справочник')
                if not 3<=len(title)<=130 or not 3<=len(slug)<=100 or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',slug):raise BadRequest('Проверьте название и адрес статьи.')
                if len(summary)>300 or not 15<=len(content)<=100000:raise BadRequest('Неверная длина содержимого.')
                if difficulty not in ('Новичкам','Справочник','Важно','Продвинутым'):raise BadRequest('Неверный тип материала.')
                status=form.get('status','draft')
                if status not in ('draft','published'):raise BadRequest('Неверный статус.')
                try:cid=int(form.get('category_id',''))
                except ValueError:raise BadRequest('Выберите раздел.')
                if not c.execute('SELECT id FROM categories WHERE id=?',(cid,)).fetchone():raise BadRequest('Раздел не существует.')
                image_path=form.get('image_path','').strip()
                if image_path and image_path!='/static/cover.jpg' and not c.execute('SELECT 1 FROM media WHERE path=?',(image_path,)).fetchone():raise BadRequest('Сначала загрузите обложку в разделе Медиафайлы.')
                feat=1 if form.get('featured')=='1' else 0;sample=1 if form.get('sample')=='1' else 0
                if a:
                    snapshot={k:a[k] for k in ('title','slug','summary','content','category_id','difficulty','image_path','status','featured','sample')}
                    c.execute('INSERT INTO revisions(article_id,user_id,snapshot,saved_at) VALUES(?,?,?,?)',(a['id'],u['id'],json.dumps(snapshot,ensure_ascii=False),db.now()))
                    c.execute('''UPDATE articles SET slug=?,title=?,summary=?,content=?,category_id=?,difficulty=?,image_path=?,status=?,featured=?,sample=?,updated_at=? WHERE id=?''',
                              (slug,title,summary,content,cid,difficulty,image_path,status,feat,sample,db.now(),a['id']))
                    target=a['id']
                else:
                    target=c.execute('''INSERT INTO articles(slug,title,summary,content,category_id,difficulty,image_path,status,featured,sample,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(slug,title,summary,content,cid,difficulty,image_path,status,feat,sample,db.now(),db.now())).lastrowid
                db.audit(c,u['id'],'article_save',target);c.commit()
                return self.redirect('/admin/article/'+str(target)+'?info='+quote('Статья сохранена'))
            if re.fullmatch(r'/admin/revision/\d+/restore',path):
                rid=int(path.split('/')[3]);r=c.execute('SELECT * FROM revisions WHERE id=?',(rid,)).fetchone()
                if not r:raise BadRequest('Версия не найдена.')
                a=c.execute('SELECT * FROM articles WHERE id=?',(r['article_id'],)).fetchone()
                if not a:raise BadRequest('Статья удалена.')
                snapshot={k:a[k] for k in ('title','slug','summary','content','category_id','difficulty','image_path','status','featured','sample')}
                c.execute('INSERT INTO revisions(article_id,user_id,snapshot,saved_at) VALUES(?,?,?,?)',(a['id'],u['id'],json.dumps(snapshot,ensure_ascii=False),db.now()))
                old=json.loads(r['snapshot']);fields=('title','slug','summary','content','category_id','difficulty','image_path','status','featured','sample')
                c.execute('UPDATE articles SET '+','.join(k+'=?' for k in fields)+',updated_at=? WHERE id=?',tuple(old[k] for k in fields)+(db.now(),a['id']))
                db.audit(c,u['id'],'revision_restore',rid);c.commit()
                return self.redirect('/admin/article/'+str(a['id'])+'?info='+quote('Версия восстановлена'))
            if path=='/admin/catalog/new' or re.fullmatch(r'/admin/catalog/item/\d+',path):
                isnew=path.endswith('/new')
                a=None if isnew else c.execute('SELECT * FROM catalog_items WHERE id=?',(int(path.split('/')[-1]),)).fetchone()
                if not isnew and not a:raise BadRequest('Карточка не найдена.')
                title=form.get('title','').strip();slug=form.get('slug','').strip();summary=form.get('summary','').strip()
                tier=form.get('tier','').strip();price=form.get('price_text','').strip();params=form.get('parameters','').strip()
                kind=form.get('kind','');status=form.get('status','draft')
                if kind not in [t[0] for t in db.CATALOG_TYPES]:raise BadRequest('Неверный каталог.')
                if not 3<=len(title)<=130 or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',slug) or len(slug)>100:raise BadRequest('Недопустимое название или адрес карточки.')
                if len(summary)>500 or len(tier)>80 or len(price)>100 or len(params)>5000 or status not in ('draft','published'):raise BadRequest('Некорректное содержимое карточки.')
                image=form.get('image_path','').strip()
                if image and image!='/static/cover.jpg' and not c.execute('SELECT 1 FROM media WHERE path=?',(image,)).fetchone():raise BadRequest('Изображение сначала нужно загрузить в медиафайлы.')
                sample=1 if form.get('sample')=='1' else 0
                if isnew:
                    ident=c.execute('INSERT INTO catalog_items(kind,slug,title,summary,tier,price_text,parameters,image_path,status,sample,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(kind,slug,title,summary,tier,price,params,image,status,sample,db.now(),db.now())).lastrowid
                else:
                    ident=a['id']
                    c.execute('UPDATE catalog_items SET kind=?,slug=?,title=?,summary=?,tier=?,price_text=?,parameters=?,image_path=?,status=?,sample=?,updated_at=? WHERE id=?',(kind,slug,title,summary,tier,price,params,image,status,sample,db.now(),ident))
                db.audit(c,u['id'],'catalog_save',ident);c.commit()
                return self.redirect('/admin/catalog/item/'+str(ident)+'?info='+quote('Карточка сохранена'))
            if path=='/admin/category/new' or re.fullmatch(r'/admin/category/\d+',path):
                title=form.get('title','').strip();slug=form.get('slug','').strip();desc=form.get('description','').strip();icon=form.get('icon','📖').strip() or '📖'
                if not 2<=len(title)<=80 or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',slug) or len(slug)>60 or len(desc)>200 or len(icon)>8:raise BadRequest('Некорректные данные категории.')
                if path.endswith('/new'):
                    n=c.execute('SELECT COALESCE(MAX(sort_order),0)+1 FROM categories').fetchone()[0]
                    c.execute('INSERT INTO categories(slug,title,description,icon,sort_order) VALUES(?,?,?,?,?)',(slug,title,desc,icon,n))
                else:
                    try:order=max(0,min(999,int(form.get('sort_order','0'))))
                    except ValueError:order=0
                    ident=int(path.split('/')[-1]);c.execute('UPDATE categories SET slug=?,title=?,description=?,icon=?,sort_order=? WHERE id=?',(slug,title,desc,icon,order,ident))
                db.audit(c,u['id'],'category_save',slug);c.commit()
                return self.redirect('/admin/categories?info='+quote('Категория сохранена'))
            if path=='/admin/users':
                if u['role']!='admin':raise NoAccess('Только администратор может создавать редакторов.')
                if not throttle(self.client_address[0],'staff',15,3600):raise BadRequest('Превышен лимит операций.')
                name=form.get('username','').strip();password=form.get('password','');role=form.get('role','editor')
                if not re.fullmatch('[A-Za-z0-9_-]{3,32}',name) or len(password)<12 or len(password)>256 or role not in ('admin','editor'):raise BadRequest('Некорректные данные редактора.')
                c.execute('INSERT INTO users(username,pass_hash,role,created_at) VALUES(?,?,?,?)',(name,db.hash_password(password),role,db.now()))
                db.audit(c,u['id'],'user_create',name);c.commit()
                return self.redirect('/admin/users?info='+quote('Редактор создан'))
            raise BadRequest('Неизвестное действие.')
        except sqlite3.IntegrityError:
            if c:c.rollback()
            self.respond('Название или адрес уже заняты. Вернитесь назад и измените значение.',409,'text/plain; charset=utf-8')
        except NoAccess as e:self.respond(str(e),403,'text/plain; charset=utf-8')
        except BadRequest as e:self.respond(str(e),400,'text/plain; charset=utf-8')
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            if c:c.rollback()
            logging.exception('POST %s',self.path)
            try:self.respond('Ошибка сервера',500,'text/plain; charset=utf-8')
            except Exception:pass
        finally:
            if c:c.close()

def serve(host=HOST,port=PORT):
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    db.init_db()
    server=ThreadingHTTPServer((host,port),Handler)
    logging.info('OBSIDIAN RUSSIA WIKI available at http://%s:%s',host,port)
    logging.info('Editor: http://%s:%s/admin',host,port)
    try:server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':serve()
