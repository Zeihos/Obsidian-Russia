"""Server-rendered HTML templates; all database/user text escaped by default."""
from html import escape
from datetime import datetime
from urllib.parse import quote
import re
import db

E=lambda x: escape(str(x if x is not None else ''),quote=True)

def date(s):
    if not s:return '—'
    try:return datetime.fromisoformat(s).strftime('%d.%m.%Y · %H:%M')
    except ValueError:return E(s)

def icon(letter):return f'<span class="tiny-icon">{E(letter)}</span>'

def avatar(username,role='member',size=''):
    user=username or '?'
    return f'<span class="avatar {size} {"avatar-staff" if role in ("admin","moderator") else ""}" aria-hidden="true">{E(user[:1].upper())}</span>'

def role_label(role):
    value={'admin':('Администратор','admin'), 'moderator':('Модератор','mod'), 'member':('Участник','member')}.get(role,('Участник','member'))
    return f'<span class="role role-{value[1]}">{value[0]}</span>'

def render_text(text):
    safe=E(text).replace('\r','')
    return '<br>'.join(safe.split('\n'))

def flash(message):
    return f'<div class="flash" role="status">{E(message)}</div>' if message else ''

def csrf_input(token):return f'<input type="hidden" name="csrf" value="{E(token)}">'

def anti_crumbs(home='Форум', crumbs=None):
    segments=[f'<a href="/">{E(home)}</a>']
    for label,url in (crumbs or []):segments.append(f'<span class="crumb-sep">/</span><a href="{E(url)}">{E(label)}</a>' if url else f'<span class="crumb-sep">/</span><span>{E(label)}</span>')
    return '<nav class="breadcrumbs" aria-label="Навигационная цепочка">'+''.join(segments)+'</nav>'

def layout(title,body,path='/',user=None,csrf='',message=''):
    user=user if user and user['user_id'] and not user['banned'] else None
    moderator=user and user['role'] in ('admin','moderator')
    account=(f'<a class="nav-account" href="/account">{avatar(user["username"],user["role"])}<span>{E(user["username"])}</span></a>' if user else '<a class="btn btn-outline btn-small" href="/login">Войти</a><a class="btn btn-red btn-small" href="/register">Регистрация</a>')
    account_mob=(f'<a href="/account">Мой профиль</a><form method="post" action="/logout">{csrf_input(csrf)}<button>Выйти</button></form>' if user else '<a href="/login">Вход</a><a href="/register">Регистрация</a>')
    admin=f'<a href="/admin" class="admin-link">Панель управления</a>' if moderator else ''
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="theme-color" content="#0c0b0d"><meta name="description" content="Официальный форум OBSIDIAN RUSSIA — обсуждения, новости, правила, жалобы и заявки">
    <title>{E(title)} — OBSIDIAN RUSSIA | Форум</title><link rel="icon" href="/static/ava.jpg" type="image/jpeg"><link rel="stylesheet" href="/static/style.css"></head>
    <body><div class="top-stripe"></div>
    <header class="header"><div class="shell header-row"><a href="/" class="brand" aria-label="OBSIDIAN RUSSIA — форум"><img src="/static/ava.jpg" alt=""><span><strong>OBSIDIAN <b>RUSSIA</b></strong><small>ОФИЦИАЛЬНЫЙ ФОРУМ</small></span></a>
    <nav class="nav-links" aria-label="Главное меню"><a class="{'active' if path=='/' else ''}" href="/">Форум</a><a class="{'active' if path.startswith('/latest') else ''}" href="/latest">Новые темы</a><a class="{'active' if path.startswith('/members') else ''}" href="/members">Участники</a><a href="https://vk.ru/obsidian_brussia" target="_blank" rel="noopener noreferrer">VK</a><a href="https://t.me/obsidian_brussia" target="_blank" rel="noopener noreferrer">Telegram</a></nav>
    <div class="header-right">{account}<button class="hamburger" aria-controls="mobile-nav" aria-expanded="false" aria-label="Открыть меню" id="menu-toggle"><span></span><span></span><span></span></button></div></div>
    <nav id="mobile-nav" class="mobile-nav" hidden><a href="/">Форум</a><a href="/latest">Новые темы</a><a href="/members">Участники</a>{admin}{account_mob}<a href="https://vk.ru/obsidian_brussia" target="_blank" rel="noopener noreferrer">ВКонтакте</a><a href="https://t.me/obsidian_brussia" target="_blank" rel="noopener noreferrer">Telegram</a></nav></header>
    <main class="shell page">{flash(message)}{body}</main>
    <footer class="footer"><div class="shell footer-row"><div class="footer-brand"><img src="/static/ava.jpg" alt=""><div><strong>OBSIDIAN RUSSIA</strong><small>СОЗДАЁМ СВОЮ ИСТОРИЮ</small></div></div><div class="footer-links"><a href="/rules">Правила</a><a href="/privacy">Конфиденциальность</a><a href="https://vk.ru/obsidian_brussia" target="_blank" rel="noopener noreferrer">ВКонтакте</a><a href="https://t.me/obsidian_brussia" target="_blank" rel="noopener noreferrer">Telegram</a></div><small class="footer-copy">© 2026 OBSIDIAN RUSSIA · Самостоятельный проект</small></div></footer>
    <script src="/static/app.js" defer></script></body></html>'''

def stats(c):
    return {'users':c.execute('SELECT COUNT(*) FROM users WHERE banned=0').fetchone()[0],
            'threads':c.execute('SELECT COUNT(*) FROM threads WHERE deleted=0').fetchone()[0],
            'posts':c.execute('SELECT COUNT(*) FROM posts p JOIN threads t ON t.id=p.thread_id WHERE p.deleted=0 AND t.deleted=0').fetchone()[0]}

def latest_threads(c,limit=5):
    return c.execute('''SELECT t.id,t.title,t.updated_at,t.locked,t.pinned,u.username,u.role,f.name AS forum_name
      FROM threads t JOIN users u ON u.id=t.user_id JOIN forums f ON f.id=t.forum_id WHERE t.deleted=0 ORDER BY t.updated_at DESC,t.id DESC LIMIT ?''',(limit,)).fetchall()

def thread_row(t,forum=False):
    badge=(' <span class="chip gold">Закреплено</span>' if t['pinned'] else '')+(' <span class="chip muted">Закрыто</span>' if t['locked'] else '')
    post_count=t['replies'] if 'replies' in t.keys() else None
    meta=(f'<span>{post_count} ответов</span>' if post_count is not None else '')
    name=E(t['username'])
    return f'''<div class="topic-row"><a class="topic-ico" href="/thread/{t['id']}" aria-label="Открыть тему">{'🔒' if t['locked'] else '▤'}</a>
       <div class="topic-main"><a class="topic-title" href="/thread/{t['id']}">{E(t['title'])}</a>{badge}<div class="topic-sub">{name} · {date(t['updated_at'])} {('· '+E(t['forum_name'])) if forum else ''}</div></div>
       {f'<div class="topic-count">{meta}</div>' if meta else ''}</div>'''

def side(c, user=None):
    s=stats(c)
    recent=latest_threads(c,5)
    news=''.join(f'<a class="side-topic" href="/thread/{t["id"]}"><span>{E(t["title"])}</span><small>{date(t["updated_at"])}</small></a>' for t in recent) or '<div class="empty-mini">Первые темы скоро появятся</div>'
    button='<a class="btn btn-red full" href="/register">Присоединиться</a>' if not user else '<a class="btn btn-red full" href="/latest">Новые обсуждения</a>'
    return f'''<aside class="sidebar"><div class="side-card"><div class="side-heading">СООБЩЕСТВО</div><div class="stat-grid"><div><b>{s['users']}</b><small>Участников</small></div><div><b>{s['threads']}</b><small>Тем</small></div><div><b>{s['posts']}</b><small>Ответов</small></div></div>{button}</div>
       <div class="side-card"><div class="side-heading">СВЕЖИЕ ОБСУЖДЕНИЯ</div>{news}</div>
       <div class="side-card social"><div class="side-heading">СЛЕДИ ЗА ПРОЕКТОМ</div><p>Все новости о разработке OBSIDIAN RUSSIA — в официальных сообществах.</p><a href="https://vk.ru/obsidian_brussia" target="_blank" rel="noopener noreferrer">ВКонтакте <span>↗</span></a><a href="https://t.me/obsidian_brussia" target="_blank" rel="noopener noreferrer">Telegram <span>↗</span></a></div></aside>'''

def home(c,user):
    categories=c.execute('SELECT * FROM categories ORDER BY sort_order,id').fetchall()
    forums=c.execute('''SELECT f.*,COUNT(DISTINCT t.id) AS topics,
       (SELECT COUNT(*) FROM posts p JOIN threads x ON x.id=p.thread_id WHERE x.forum_id=f.id AND x.deleted=0 AND p.deleted=0) AS answers,
       (SELECT x.id FROM threads x WHERE x.forum_id=f.id AND x.deleted=0 ORDER BY x.updated_at DESC,x.id DESC LIMIT 1) AS last_id,
       (SELECT x.title FROM threads x WHERE x.forum_id=f.id AND x.deleted=0 ORDER BY x.updated_at DESC,x.id DESC LIMIT 1) AS last_title
       FROM forums f LEFT JOIN threads t ON t.forum_id=f.id AND t.deleted=0 GROUP BY f.id ORDER BY f.sort_order,f.id''').fetchall()
    blocks=''
    for cat in categories:
        subset=[f for f in forums if f['category_id']==cat['id'] and not f['archived']]
        rows=''
        for f in subset:
            last=f'<a href="/thread/{f["last_id"]}">{E(f["last_title"])}</a>' if f['last_id'] else '<span class="quiet">Пока нет тем</span>'
            rows+=f'''<a class="forum-row" href="/forum/{f['id']}"><span class="forum-symbol">{('◆' if f['staff_only'] else '▤')}</span>
            <span class="forum-detail"><strong>{E(f['name'])}</strong><small>{E(f['description'])}</small></span>
            <span class="forum-numbers"><b>{f['topics']}</b><small>тем</small></span><span class="forum-last" >{last if not f['last_id'] else E(f['last_title'])}<small>Последнее обсуждение</small></span><span class="arrow">›</span></a>'''
        blocks+=f'''<section class="forum-block"><div class="section-bar"><div><h2>{E(cat['title'])}</h2><p>{E(cat['description'])}</p></div><span>0{cat['sort_order']+1}</span></div>{rows}</section>'''
    stat=stats(c)
    splash='''<div class="hero"><div class="hero-overlay"><span class="eyebrow"><span class="status-dot"></span> ОФИЦИАЛЬНОЕ СООБЩЕСТВО</span><div class="hero-actions"><a class="btn btn-red" href="/latest">Смотреть обсуждения ↗</a><a class="btn btn-glass" href="https://vk.ru/obsidian_brussia" target="_blank" rel="noopener noreferrer">Сообщество VK</a></div></div></div>'''
    return f'''{splash}<div class="heading-row"><div><span class="eyebrow red-text">НАВИГАЦИЯ</span><h1>ФОРУМ <em>OBSIDIAN RUSSIA</em></h1><p>Новости проекта, игровые разделы, обращения и общение участников.</p></div><form class="search" action="/search" method="get"><input name="q" placeholder="Найти обсуждение..." aria-label="Поиск по форуму"><button aria-label="Поиск">⌕</button></form></div><div class="columns"><div class="main-column">{blocks}</div>{side(c,user)}</div>'''

def listing(c,forum,rows,total,page,user):
    crumbs=anti_crumbs(crumbs=[(forum['name'],'')]); limit=20
    threadlist=''.join(thread_row(t) for t in rows) if rows else '<div class="empty">Тем пока нет. Будь первым, кто начнёт обсуждение.</div>'
    make=(f'<a class="btn btn-red" href="/thread/new?forum={forum["id"]}">＋ Создать тему</a>' if user and (not forum['staff_only'] or user['role'] in ('admin','moderator')) and not forum['archived'] else '')
    if not user:make='<a class="btn btn-outline" href="/login">Войти, чтобы создать тему</a>'
    pages=pagination(page,total,limit,f'/forum/{forum["id"]}?page=')
    return f'''{crumbs}<div class="view-heading"><div><span class="eyebrow red-text">РАЗДЕЛ ФОРУМА</span><h1>{E(forum['name'])}</h1><p>{E(forum['description'])}</p></div>{make}</div><div class="columns"><section class="main-column"><div class="list-panel"><div class="list-top"><strong>ОБСУЖДЕНИЯ</strong><span>{total} тем</span></div>{threadlist}</div>{pages}</section>{side(c,user)}</div>'''

def pagination(page,count,step,prefix):
    pages=max(1,(count+step-1)//step)
    if pages<=1:return ''
    a=max(1,page-3);b=min(pages,page+3)
    links=''.join(f'<a class="{("selected" if n==page else "")}" href="{E(prefix+str(n))}">{n}</a>' for n in range(a,b+1))
    return f'<nav class="pagination" aria-label="Страницы">{links}</nav>'

def thread_page(c,thread,posts,post_total,page,user,csrf):
    staff=user and user['role'] in ('moderator','admin')
    owner=user and user['user_id']==thread['user_id']
    follow=user and c.execute('SELECT 1 FROM follows WHERE user_id=? AND thread_id=?',(user['user_id'],thread['id'])).fetchone()
    crumb=anti_crumbs(crumbs=[(thread['forum_name'],f'/forum/{thread["forum_id"]}'),(thread['title'],'')])
    actions=''
    if user:
        actions+=f'<form method="post" action="/thread/{thread["id"]}/follow" class="inline-form">{csrf_input(csrf)}<button class="btn btn-outline btn-small">{"Отписаться" if follow else "☆ Подписаться"}</button></form>'
    if staff:
        for act,label in [('pin','Открепить' if thread['pinned'] else 'Закрепить'),('lock','Открыть' if thread['locked'] else 'Закрыть'),('delete','Удалить')]:
            actions+=f'<form method="post" action="/moderate/thread/{thread["id"]}/{act}" class="inline-form" data-confirm="{E(label)} тему?">{csrf_input(csrf)}<button class="btn btn-outline btn-small">{E(label)}</button></form>'
    if (owner or staff):actions+=f'<a class="btn btn-outline btn-small" href="/thread/{thread["id"]}/edit">Редактировать</a>'
    op=post_card(thread,initial=True,thread_id=thread['id'],user=user,csrf=csrf)
    responses=''.join(post_card(p,thread_id=thread['id'],user=user,csrf=csrf) for p in posts) if posts else '<div class="empty">Ответов пока нет. Начни обсуждение!</div>'
    form=(f'''<div class="panel reply-panel" id="reply"><h3>ОСТАВИТЬ ОТВЕТ</h3><form method="post" action="/thread/{thread['id']}/reply">{csrf_input(csrf)}<textarea name="body" maxlength="10000" minlength="2" rows="6" required placeholder="Напиши своё сообщение..." aria-label="Текст ответа"></textarea><div class="form-foot"><small>Уважай других участников. HTML-разметка не исполняется.</small><button class="btn btn-red">Отправить ответ</button></div></form></div>''' if user and not thread['locked'] else ('<div class="notice">Тема закрыта для ответов.</div>' if thread['locked'] else '<div class="notice">Чтобы участвовать в обсуждении, <a href="/login">войди в аккаунт</a>.</div>'))
    return f'''{crumb}<div class="view-heading topic-head"><div><span class="eyebrow red-text">ОБСУЖДЕНИЕ #{thread['id']}</span><h1>{E(thread['title'])}</h1><p>Создал {E(thread['username'])} · {date(thread['created_at'])} · {thread['views']} просмотров</p></div></div>
     <div class="thread-tools">{actions}</div><div class="columns"><article class="main-column">{op}<div class="response-count">ОТВЕТЫ <span>{post_total}</span></div>{responses}{pagination(page,post_total,20,f'/thread/{thread["id"]}?page=')}{form}</article>{side(c,user)}</div>'''

def post_card(row,thread_id,user,csrf,initial=False):
    name=row['username'];role=row['role']
    owner=user and user['user_id']==row['user_id']
    staff=user and user['role'] in ('admin','moderator')
    post_id=row['id'] if not initial else None
    opts=''
    if user:
        if owner or staff:
            edit_href=f'/thread/{thread_id}/edit' if initial else f'/post/{post_id}/edit'
            opts+=f'<a href="{edit_href}">Редактировать</a>'
        if not initial:
            if owner or staff:
                opts+=f'<form class="inline-form" action="/post/{post_id}/delete" method="post" data-confirm="Удалить сообщение?">{csrf_input(csrf)}<button>Удалить</button></form>'
            opts+=f'<a href="/report?post={post_id}">Пожаловаться</a>'
        else:opts+=f'<a href="/report?thread={thread_id}">Пожаловаться</a>'
    return f'''<div class="post-card" id="post-{post_id or 'first'}"><div class="post-author">{avatar(name,role,'avatar-large')}<div><a href="/user/{row['user_id']}" class="username">{E(name)}</a>{role_label(role)}</div><small>Участник OBSIDIAN</small></div><div class="post-main"><div class="post-meta"><span>{'Первое сообщение' if initial else 'Ответ'} · {date(row['created_at'])}</span><span>#{'1' if initial else post_id}</span></div><div class="post-body">{render_text(row['body'])}</div><div class="post-actions">{opts}</div></div></div>'''

def new_thread_form(forum,csrf,thread=None):
    edit=thread is not None
    action=f'/thread/{thread["id"]}/edit' if edit else '/thread/new'
    back=f'/thread/{thread["id"]}' if edit else f'/forum/{forum["id"]}'
    return f'''{anti_crumbs(crumbs=[(forum['name'],f'/forum/{forum['id']}'),(('Редактирование темы' if edit else 'Новая тема'),'')])}<section class="form-page"><span class="eyebrow red-text">{E(forum['name'])}</span><h1>{'РЕДАКТИРОВАТЬ ТЕМУ' if edit else 'СОЗДАТЬ ТЕМУ'}</h1><form class="panel form-card" method="post" action="{action}">{csrf_input(csrf)}<input type="hidden" name="forum" value="{forum['id']}"><label>Название темы <input name="title" maxlength="130" minlength="5" required placeholder="О чём пойдёт обсуждение?" value="{E(thread['title'] if edit else '')}"></label><label>Содержание <textarea name="body" maxlength="20000" minlength="10" rows="13" required placeholder="Расскажи подробности...">{E(thread['body'] if edit else '')}</textarea></label><p class="helper">Для жалоб указывай дату, обстоятельства и подтверждающие материалы. Публикуй только допустимые к разглашению сведения.</p><div class="form-foot"><a href="{back}" class="btn btn-outline">Отмена</a><button class="btn btn-red">{'Сохранить' if edit else 'Опубликовать тему'}</button></div></form></section>'''

def edit_post_form(post,csrf):
    return f'''{anti_crumbs(crumbs=[('Редактирование ответа','')])}<section class="form-page"><h1>РЕДАКТИРОВАТЬ ОТВЕТ</h1><form class="panel form-card" action="/post/{post['id']}/edit" method="post">{csrf_input(csrf)}<label>Текст ответа<textarea name="body" maxlength="10000" minlength="2" rows="12" required>{E(post['body'])}</textarea></label><div class="form-foot"><a class="btn btn-outline" href="/thread/{post['thread_id']}">Отмена</a><button class="btn btn-red">Сохранить</button></div></form></section>'''

def auth_form(mode,csrf):
    register=mode=='register'
    inputs=(f'<label>Логин <input name="username" minlength="3" maxlength="24" pattern="[A-Za-z0-9_]+" required autocomplete="username" placeholder="Придумай логин"></label><label>Email <input name="email" type="email" maxlength="200" required autocomplete="email" placeholder="name@example.com"></label>' if register else '<label>Логин или email <input name="identity" maxlength="200" autocomplete="username" required placeholder="Логин или email"></label>')
    return f'''<section class="auth-wrap"><div class="auth-intro"><img src="/static/ava.jpg" alt="OBSIDIAN RUSSIA"><span class="eyebrow red-text">ОФИЦИАЛЬНЫЙ ФОРУМ</span><h1>{'СОЗДАЙ АККАУНТ' if register else 'С ВОЗВРАЩЕНИЕМ'}</h1><p>{'Присоединяйся к сообществу OBSIDIAN RUSSIA и участвуй в обсуждениях.' if register else 'Войди в аккаунт, чтобы публиковать темы, отвечать и следить за обсуждениями.'}</p></div><form method="post" class="panel form-card auth-card" action="/{mode}">{csrf_input(csrf)}{inputs}<label>Пароль <input type="password" name="password" minlength="{'10' if register else '1'}" maxlength="128" required autocomplete="{'new-password' if register else 'current-password'}" placeholder="{'Не менее 10 символов' if register else 'Введите пароль'}"></label>{'<label>Повтори пароль <input type="password" name="confirm" minlength="10" maxlength="128" required autocomplete="new-password" placeholder="Повтори пароль"></label>' if register else ''}<button class="btn btn-red full">{'Зарегистрироваться' if register else 'Войти'}</button><p class="form-switch">{'Есть аккаунт? <a href="/login">Войти</a>' if register else 'Впервые здесь? <a href="/register">Создать аккаунт</a>'}</p></form></section>'''

def account(c,user,csrf,sso_enabled=False):
    my_threads=c.execute('SELECT id,title,created_at FROM threads WHERE user_id=? AND deleted=0 ORDER BY id DESC LIMIT 12',(user['user_id'],)).fetchall()
    threads=''.join(f'<a class="side-topic" href="/thread/{x["id"]}">{E(x["title"])} <small>{date(x["created_at"])}</small></a>' for x in my_threads) or '<div class="empty">Ты ещё не создал ни одной темы.</div>'
    watched=c.execute('''SELECT t.id,t.title,t.updated_at,f.last_seen FROM follows f JOIN threads t ON t.id=f.thread_id WHERE f.user_id=? AND t.deleted=0 ORDER BY t.updated_at DESC LIMIT 12''',(user['user_id'],)).fetchall()
    following=''.join(f'<a class="side-topic" href="/thread/{x["id"]}">{E(x["title"])}<small>{date(x["updated_at"])}</small></a>' for x in watched) or '<div class="empty">Нет подписок на темы.</div>'
    admin='<a class="btn btn-outline" href="/admin">Панель управления</a>' if user['role'] in ('admin','moderator') else ''
    linked=c.execute('SELECT 1 FROM sso_accounts WHERE user_id=?',(user['user_id'],)).fetchone()
    password_area=('<p class="helper">Аккаунт связан с OBSIDIAN RUSSIA. Пароль изменяется на основном сайте, а не на форуме.</p>' if linked else f'<form action="/account/password" method="post">{csrf_input(csrf)}<label>Текущий пароль<input type="password" name="old" required></label><label>Новый пароль (10+ символов)<input type="password" name="password" minlength="10" maxlength="128" required></label><button class="btn btn-red">Сменить пароль</button></form>')
    email_display='Учётная запись OBSIDIAN RUSSIA' if linked else 'Email: '+E(user['email'])
    link_form=(
        f'''<div class="panel form-card"><h2>ПРИВЯЗКА АККАУНТА OBSIDIAN RUSSIA</h2>
        <p class="helper">Сохрани свои темы, ответы и имя на форуме, подключив аккаунт основного сайта. Подтверди текущий пароль форума, затем войди на сайте.</p>
        <form method="post" action="/sso/link/start">{csrf_input(csrf)}
        <label>Текущий пароль форума<input type="password" name="password" maxlength="128" required autocomplete="current-password"></label>
        <button class="btn btn-red">Привязать аккаунт сайта</button></form>
        <p class="helper">После привязки прежний пароль форума перестанет работать: вход будет только через сайт. Если аккаунт сайта уже связан с другим форумным профилем, автоматического объединения не будет. Для модераторов и администраторов самостоятельная привязка недоступна.</p></div>'''
        if sso_enabled and not linked and user['role']=='member' else ''
    )
    active_sessions=c.execute('SELECT COUNT(*) FROM sessions WHERE user_id=? AND expires_at>?',(user['user_id'],db.now())).fetchone()[0]
    session_controls=f'''<div class="panel form-card"><h2>АКТИВНЫЕ СЕАНСЫ</h2><p class="helper">Входов на форум: <strong>{active_sessions}</strong></p><form method="post" action="/account/sessions/close-others">{csrf_input(csrf)}<button class="btn btn-outline">Завершить другие сеансы</button></form><form method="post" action="/account/sessions/logout-all">{csrf_input(csrf)}<button class="btn btn-outline">Выйти на всех устройствах</button></form><p class="helper">Это закрывает сеансы форума, но не сайта и не Wiki.</p></div>'''
    return f'''{anti_crumbs(crumbs=[('Мой профиль','')])}<div class="profile-header">{avatar(user['username'],user['role'],'avatar-xl')}<div><span class="eyebrow red-text">ЛИЧНЫЙ КАБИНЕТ</span><h1>{E(user['username'])}</h1><div class="profile-meta">{role_label(user['role'])} · На форуме с {date(user['joined_at'])}</div></div>{admin}</div><div class="account-grid"><div class="panel form-card"><h2>НАСТРОЙКИ АККАУНТА</h2><p class="helper">{email_display}</p>{password_area}<form method="post" action="/logout" class="logout-form">{csrf_input(csrf)}<button class="btn btn-outline">Выйти из аккаунта</button></form></div>{link_form}{session_controls}<div class="panel dashboard-list"><h2>МОИ ТЕМЫ</h2>{threads}</div><div class="panel dashboard-list"><h2>ПОДПИСКИ</h2>{following}</div></div>'''

def member_list(c):
    users=c.execute('SELECT id,username,role,joined_at FROM users WHERE banned=0 ORDER BY joined_at DESC,id DESC LIMIT 100').fetchall()
    cards=''.join(f'<a class="member-card" href="/user/{u["id"]}">{avatar(u["username"],u["role"])}<span><b>{E(u["username"])}</b><small>{role_label(u["role"])} · {date(u["joined_at"])}</small></span></a>' for u in users)
    return f'''{anti_crumbs(crumbs=[('Участники','')])}<div class="view-heading"><div><span class="eyebrow red-text">СООБЩЕСТВО</span><h1>УЧАСТНИКИ</h1><p>Активные пользователи форума OBSIDIAN RUSSIA.</p></div></div><div class="member-grid">{cards}</div>'''

def user_profile(c,u):
    count=c.execute('SELECT COUNT(*) FROM threads WHERE user_id=? AND deleted=0',(u['id'],)).fetchone()[0]
    posts=c.execute('SELECT COUNT(*) FROM posts WHERE user_id=? AND deleted=0',(u['id'],)).fetchone()[0]
    threads=c.execute('SELECT id,title,created_at FROM threads WHERE user_id=? AND deleted=0 ORDER BY created_at DESC LIMIT 12',(u['id'],)).fetchall()
    items=''.join(f'<a class="side-topic" href="/thread/{t["id"]}">{E(t["title"])}<small>{date(t["created_at"])}</small></a>' for t in threads) or '<div class="empty">Тем пока нет.</div>'
    return f'''{anti_crumbs(crumbs=[('Участники','/members'),(u['username'],'')])}<div class="profile-header">{avatar(u['username'],u['role'],'avatar-xl')}<div><span class="eyebrow red-text">ПРОФИЛЬ УЧАСТНИКА</span><h1>{E(u['username'])}</h1>{role_label(u['role'])}<p>С нами с {date(u['joined_at'])}</p></div></div><div class="profile-stat"><div><strong>{count}</strong><small>Тем создано</small></div><div><strong>{posts}</strong><small>Ответов</small></div></div><section class="panel dashboard-list"><h2>ТЕМЫ ПОЛЬЗОВАТЕЛЯ</h2>{items}</section>'''

def latest_page(c,rows,total,page,user,mode='latest',q=''):
    title='РЕЗУЛЬТАТЫ ПОИСКА' if mode=='search' else 'НОВЫЕ ТЕМЫ'
    items=''.join(thread_row(t,True) for t in rows) or '<div class="empty">По заданным условиям ничего не найдено.</div>'
    prefix=f'/search?q={quote(q)}&page=' if mode=='search' else '/latest?page='
    return f'''{anti_crumbs(crumbs=[('Поиск' if mode=='search' else 'Новые темы','')])}<div class="view-heading"><div><span class="eyebrow red-text">ОБСУЖДЕНИЯ</span><h1>{title}</h1><p>{('Результаты по запросу: '+E(q)) if mode=='search' else 'Самые свежие обсуждения на форуме.'}</p></div><form class="search" method="get" action="/search"><input name="q" maxlength="80" value="{E(q)}" placeholder="Поиск по темам"><button>⌕</button></form></div><div class="columns"><section class="main-column"><div class="list-panel"><div class="list-top"><strong>ТЕМЫ</strong><span>Всего: {total}</span></div>{items}</div>{pagination(page,total,20,prefix)}</section>{side(c,user)}</div>'''

def report_form(thread_id,post_id,csrf):
    return f'''{anti_crumbs(crumbs=[('Сообщить о нарушении','')])}<div class="form-page"><h1>СООБЩИТЬ О НАРУШЕНИИ</h1><p>Жалоба поступит модераторам форума.</p><form method="post" action="/report" class="panel form-card">{csrf_input(csrf)}<input type="hidden" name="thread_id" value="{E(thread_id or '')}"><input type="hidden" name="post_id" value="{E(post_id or '')}"><label>Причина обращения<textarea name="reason" maxlength="1500" minlength="10" rows="7" required placeholder="Опиши, какие правила нарушены..."></textarea></label><button class="btn btn-red">Отправить жалобу</button></form></div>'''

def admin_page(c,user,csrf,tab):
    own=user['role']=='admin';staff=user['role'] in ('admin','moderator')
    tabs=[('overview','Обзор'),('reports','Жалобы'),('threads','Темы')]+([('users','Пользователи'),('forums','Разделы'),('audit','Журнал')] if own else [])
    tabbar='<nav class="admin-tabs">'+''.join(f'<a class="{("current" if tab==key else "")}" href="/admin?tab={key}">{E(label)}</a>' for key,label in tabs)+'</nav>'
    inner=''
    if tab=='overview':
        s=stats(c);reports=c.execute("SELECT COUNT(*) FROM reports WHERE status='open'").fetchone()[0]
        inner=f'''<div class="admin-stats"><div><strong>{s['users']}</strong><span>Участников</span></div><div><strong>{s['threads']}</strong><span>Тем</span></div><div><strong>{s['posts']}</strong><span>Ответов</span></div><div><strong>{reports}</strong><span>Открытых жалоб</span></div></div><div class="notice">Управление форумом доступно согласно назначенной роли. Изменения сохраняются в SQLite.</div>'''
    if tab=='reports':
        reports=c.execute('''SELECT r.*,u.username AS reporter,(SELECT title FROM threads WHERE id=r.thread_id) AS topic
          FROM reports r JOIN users u ON u.id=r.reporter_id ORDER BY (r.status='open') DESC,r.id DESC LIMIT 100''').fetchall()
        for r in reports:
            link=f'/thread/{r["thread_id"]}' if r['thread_id'] else f'/thread/{c.execute("SELECT thread_id FROM posts WHERE id=?",(r["post_id"],)).fetchone()[0]}'
            inner+=f'''<div class="admin-item"><div><strong>Жалоба #{r['id']} · {E(r['reporter'])}</strong><p>{E(r['reason'])}</p><small>{date(r['created_at'])} · {E(r['status'])} · <a href="{link}">К публикации</a></small></div>{f'<form method="post" action="/admin/report/{r["id"]}/close">{csrf_input(csrf)}<button class="btn btn-outline btn-small">Закрыть</button></form>' if r['status']=='open' else ''}</div>'''
        if not reports:inner='<div class="empty">Жалоб пока нет.</div>'
    if tab=='threads':
        rows=c.execute('''SELECT t.id,t.title,t.deleted,t.locked,t.pinned,u.username FROM threads t JOIN users u ON u.id=t.user_id ORDER BY t.id DESC LIMIT 75''').fetchall()
        inner=''.join(f'''<div class="admin-item"><div><a href="/thread/{t['id']}">{E(t['title'])}</a><small>{E(t['username'])} · {'Удалена' if t['deleted'] else 'Активна'} · {'Закрыта' if t['locked'] else 'Открыта'}</small></div><div class="admin-actions">{''.join(f'<form method="post" action="/moderate/thread/{t["id"]}/{act}">{csrf_input(csrf)}<button class="btn btn-outline btn-small">{E(label)}</button></form>' for act,label in [('restore','Вернуть') if t['deleted'] else ('delete','Удалить'),('lock','Открыть' if t['locked'] else 'Закрыть')])}</div></div>''' for t in rows) or '<div class="empty">Тем пока нет</div>'
    if tab=='users' and own:
        rows=c.execute('SELECT id,username,email,role,banned,joined_at FROM users ORDER BY id DESC LIMIT 150').fetchall()
        inner=''.join(f'''<div class="admin-item"><div><strong>{E(u['username'])}</strong><small>{E(u['email'])} · ID {u['id']} {'· Заблокирован' if u['banned'] else ''}</small></div><form class="admin-actions" method="post" action="/admin/user/{u['id']}">{csrf_input(csrf)}<select name="role" aria-label="Роль {E(u['username'])}">{''.join(f'<option value="{x}" {"selected" if x==u['role'] else ""}>{y}</option>' for x,y in [('member','Участник'),('moderator','Модератор'),('admin','Администратор')])}</select><label class="inline-check"><input type="checkbox" name="banned" value="1" {'checked' if u['banned'] else ''}> Бан</label><button class="btn btn-red btn-small">Сохранить</button></form></div>''' for u in rows)
    if tab=='forums' and own:
        rows=c.execute('SELECT f.*,c.title AS category FROM forums f JOIN categories c ON c.id=f.category_id ORDER BY c.sort_order,f.sort_order').fetchall()
        inner=''.join(f'''<div class="admin-item"><div><strong>{E(f['name'])}</strong><small>{E(f['category'])} · ID {f['id']}</small></div><form class="edit-forum" method="post" action="/admin/forum/{f['id']}">{csrf_input(csrf)}<input name="name" value="{E(f['name'])}" maxlength="90" aria-label="Название раздела"><input name="description" value="{E(f['description'])}" maxlength="240" aria-label="Описание раздела"><label class="inline-check"><input type="checkbox" name="staff_only" value="1" {'checked' if f['staff_only'] else ''}> Только команда</label><label class="inline-check"><input type="checkbox" name="archived" value="1" {'checked' if f['archived'] else ''}> Архив</label><button class="btn btn-red btn-small">Сохранить</button></form></div>''' for f in rows)
        inner+='<h3>КАТЕГОРИИ ФОРУМА</h3>'
        for cat in c.execute('SELECT * FROM categories ORDER BY sort_order,id'):
            inner+=f'''<div class="admin-item"><form class="edit-forum" action="/admin/category/{cat['id']}" method="post">{csrf_input(csrf)}<input name="title" maxlength="90" value="{E(cat['title'])}" required aria-label="Название категории"><input name="description" maxlength="240" value="{E(cat['description'])}" aria-label="Описание категории"><button class="btn btn-outline btn-small">Обновить категорию</button></form></div>'''
        inner+=f'''<form class="panel form-card" method="post" action="/admin/category/new">{csrf_input(csrf)}<h3>НОВАЯ КАТЕГОРИЯ</h3><label>Название<input name="title" maxlength="90" required></label><label>Описание<input name="description" maxlength="240"></label><button class="btn btn-red">Добавить категорию</button></form>'''
        choices=''.join(f'<option value="{r["id"]}">{E(r["title"])}</option>' for r in c.execute('SELECT * FROM categories ORDER BY sort_order'))
        inner+=f'''<form class="panel form-card" action="/admin/forum/new" method="post">{csrf_input(csrf)}<h3>НОВЫЙ РАЗДЕЛ</h3><label>Категория<select name="category_id">{choices}</select></label><label>Название<input name="name" maxlength="90" required></label><label>Описание<input name="description" maxlength="240"></label><button class="btn btn-red">Добавить раздел</button></form>'''
    if tab=='audit' and own:
        rows=c.execute('SELECT a.*,u.username FROM audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 100').fetchall()
        inner=''.join(f'<div class="admin-item"><div><strong>{E(x["action"])} · {E(x["username"] or "system")}</strong><small>{E(x["target"])} · {date(x["created_at"])}</small></div></div>' for x in rows) or '<div class="empty">Действий пока нет.</div>'
    return f'''{anti_crumbs(crumbs=[('Панель управления','')])}<div class="view-heading"><div><span class="eyebrow red-text">КОМАНДА OBSIDIAN</span><h1>ПАНЕЛЬ УПРАВЛЕНИЯ</h1><p>Модерация, настройки разделов и управление сообществом.</p></div></div>{tabbar}<div class="admin-panel">{inner}</div>'''

def rules():
    return '''<section class="static-content"><span class="eyebrow red-text">ИНФОРМАЦИЯ</span><h1>ПРАВИЛА ФОРУМА</h1><div class="panel form-card"><h2>1. Общение</h2><p>Общайся уважительно. Запрещены оскорбления, угрозы, травля, дискриминация и провокации.</p><h2>2. Публикации</h2><p>Темы должны соответствовать разделу. Запрещены спам, реклама без разрешения, мошенничество, публикация чужих персональных данных и вредоносные ссылки.</p><h2>3. Жалобы</h2><p>Предоставляй проверяемую информацию и доказательства, не публикуя секреты, личные данные третьих лиц или материалы, которыми не имеешь права делиться.</p><h2>4. Модерация</h2><p>Команда вправе закрывать, скрывать и удалять публикации, ограничивать доступ к форуму за нарушения. Решения могут быть обжалованы в соответствующем разделе.</p><h2>5. Изменения</h2><p>Правила форума могут дополняться. Условия игровых серверов будут опубликованы отдельно при запуске.</p></div></section>'''

def privacy():
    return '''<section class="static-content"><span class="eyebrow red-text">ПЕРСОНАЛЬНЫЕ ДАННЫЕ</span><h1>КОНФИДЕНЦИАЛЬНОСТЬ</h1><div class="panel form-card"><p>Это предварительная информационная страница для локальной сборки. Перед публичным запуском владелец форума обязан опубликовать полную политику с данными оператора, сроками хранения, правовыми основаниями, порядком удаления и контактами.</p><h2>Что сохраняет текущий движок</h2><p>Логин, адрес электронной почты, стойкий хеш пароля, дату регистрации, темы, ответы, жалобы, роли и сессии. Данные хранятся в локальной базе SQLite администратора форума.</p><h2>Файлы cookie</h2><p>Используется технический cookie сессии с флагами HttpOnly и SameSite. Secure активируется при размещении через HTTPS.</p><h2>Важно</h2><p>Не размещай форум публично, пока не определены контакты владельца, политика конфиденциальности и порядок обработки данных.</p></div></section>'''

def not_found():
    return '''<div class="notfound"><span>404</span><h1>СТРАНИЦА НЕ НАЙДЕНА</h1><p>Возможно, тема перемещена или удалена.</p><a class="btn btn-red" href="/">На главную</a></div>'''
