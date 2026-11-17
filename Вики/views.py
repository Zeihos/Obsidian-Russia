"""HTML rendering of OBSIDIAN RUSSIA WIKI. Every user-controlled string is escaped."""
import html, re, json
from datetime import datetime
from urllib.parse import quote

SITE='OBSIDIAN RUSSIA'
VK='https://vk.ru/obsidian_brussia'
TG='https://t.me/obsidian_brussia'
E=lambda x:html.escape(str(x if x is not None else ''),quote=True)

ICONS={'start':'🚀','transport':'🚘','jobs':'💼','factions':'🏛️','property':'🏘️','business':'🏪','items':'🎒','systems':'⚙️','community':'🛡️'}

def date(s):
    if not s:return '—'
    try:return datetime.fromisoformat(s).strftime('%d.%m.%Y')
    except ValueError:return E(s[:10])

def em_link(s):
    # Inline elements are re-escaped after matching each raw token; hyperlinks limited to safe protocols.
    chunks=re.split(r'(\[[^\]\n]{1,150}\]\((?:https?://|/)[^\s)]{1,500}\)|\*\*[^*\n]+\*\*|`[^`\n]+`)',s)
    out=[]
    for x in chunks:
        if x.startswith('**') and x.endswith('**'):
            out.append('<strong>'+E(x[2:-2])+'</strong>')
        elif x.startswith('`') and x.endswith('`'):
            out.append('<code>'+E(x[1:-1])+'</code>')
        elif x.startswith('[') and '](' in x and x.endswith(')'):
            title,link=x[1:-1].split('](',1)
            if link.startswith(('https://','http://','/')) and not link.startswith('//') and not any(z in link for z in '"<>\\'):
                out.append('<a href="'+E(link)+'"'+(' target="_blank" rel="noopener noreferrer"' if link.startswith('http') else '')+'>'+E(title)+'</a>')
            else:out.append(E(x))
        else:out.append(E(x))
    return ''.join(out)

def md(content):
    blocks=[]; in_list=False; count=0
    for raw in content.replace('\r\n','\n').split('\n'):
        line=raw.strip()
        if not line:
            if in_list:blocks.append('</ul>');in_list=False
            continue
        if line.startswith('- '):
            if not in_list:blocks.append('<ul>');in_list=True
            blocks.append('<li>'+em_link(line[2:])+'</li>')
            continue
        if in_list:blocks.append('</ul>');in_list=False
        if line.startswith('### '):blocks.append('<h3>'+em_link(line[4:])+'</h3>')
        elif line.startswith('## '):
            count+=1;blocks.append(f'<h2 id="section-{count}">'+em_link(line[3:])+'</h2>')
        elif line.startswith('# '):blocks.append('<h1>'+em_link(line[2:])+'</h1>')
        elif line.startswith('> '):blocks.append('<blockquote>'+em_link(line[2:])+'</blockquote>')
        elif line=='---':blocks.append('<hr>')
        else:blocks.append('<p>'+em_link(line)+'</p>')
    if in_list:blocks.append('</ul>')
    return '\n'.join(blocks)

def nav(categories,current=''):
    return ''.join(f'<a class="drawer-cat {"active" if c["slug"]==current else ""}" href="/category/{E(c["slug"])}"><span>{E(c["icon"])}</span>{E(c["title"])}</a>' for c in categories)

def base(title,body,categories=(),user=None,active='',description='',sidebar=False):
    is_staff=bool(user)
    head=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#10090b"><meta name="description" content="{E(description or 'OBSIDIAN RUSSIA WIKI — официальная база знаний игрового проекта.')}">
<meta property="og:type" content="website"><meta property="og:title" content="{E(title)} — OBSIDIAN RUSSIA WIKI"><meta property="og:description" content="{E(description or 'Руководства, каталоги и помощь по OBSIDIAN RUSSIA')}">
<meta property="og:image" content="/static/cover.jpg"><link rel="icon" type="image/jpeg" href="/static/ava.jpg">
<title>{E(title)} · OBSIDIAN RUSSIA WIKI</title><link rel="stylesheet" href="/static/style.css"><script src="/static/app.js" defer></script></head><body>
<div class="noise"></div><div class="topline"><div class="container top-inner"><span class="top-tag"><span class="live-dot"></span> БАЗА ЗНАНИЙ ПРОЕКТА</span><span class="top-social"><a href="{VK}" target="_blank" rel="noopener">ВКонтакте</a><a href="{TG}" target="_blank" rel="noopener">Telegram</a></span></div></div>
<header class="site-header"><div class="container header-inner">
<a class="brand" href="/" aria-label="OBSIDIAN RUSSIA WIKI"><span class="brand-mark"><img src="/static/ava.jpg" alt="Эмблема OBSIDIAN RUSSIA"></span><span><strong>OBSIDIAN <em>RUSSIA</em></strong><small>WIKI / БАЗА ЗНАНИЙ</small></span></a>
<nav class="desktop-nav" aria-label="Навигация"><a class="{'active' if active=='home' else ''}" href="/">Главная</a><a class="{'active' if active=='catalog' else ''}" href="/categories">Разделы</a><a class="{'active' if active=='articles' else ''}" href="/articles">Все статьи</a><a class="{'active' if active=='catalog' else ''}" href="/catalog">Каталог</a><a class="{'active' if active=='about' else ''}" href="/about">О Wiki</a></nav>
<div class="header-actions"><button class="search-top" type="button" data-search-open><span>⌕</span> <span class="search-title">Поиск</span><kbd>Ctrl K</kbd></button>{'<a class="staff-link" href="/admin">Панель</a>' if is_staff else '<a class="staff-link" href="/login">Вход</a>'}<button type="button" class="hamburger" aria-label="Открыть меню" aria-expanded="false" data-menu-toggle>☰</button></div></div></header>
<div class="mobile-drawer" id="mobileDrawer" aria-hidden="true"><div class="drawer-links"><a href="/">Главная</a><a href="/categories">Категории</a><a href="/articles">Все статьи</a><a href="/catalog">Каталог</a><a href="/about">О Wiki</a></div><small>КАТЕГОРИИ</small>{nav(categories)}</div>
<main id="mainContent">'''
    footer=f'''</main><footer class="footer"><div class="container"><div class="footer-top"><div class="footer-brand"><img src="/static/ava.jpg" alt=""><div><b>OBSIDIAN <em>RUSSIA</em></b><small>ЗНАНИЯ ДЛЯ ТВОЕЙ ИСТОРИИ</small></div></div><p>Независимая база знаний проекта OBSIDIAN RUSSIA. Информация об игровых механиках уточняется по мере развития проекта.</p><div class="foot-social"><a href="{VK}" target="_blank" rel="noopener noreferrer">VK</a><a href="{TG}" target="_blank" rel="noopener noreferrer">TG</a></div></div><div class="footer-bottom"><span>© {datetime.now().year} OBSIDIAN RUSSIA · Wiki</span><span><a href="/about">О проекте</a><a href="/privacy">Конфиденциальность</a><a href="/sitemap.xml">Карта сайта</a></span></div></div></footer>
<div class="search-modal" id="searchModal" aria-hidden="true"><div class="search-shade" data-search-close></div><div class="search-dialog" role="dialog" aria-modal="true" aria-label="Поиск по Wiki"><form action="/search" method="get"><div class="modal-search-row"><span>⌕</span><input id="globalSearch" name="q" placeholder="Что хочешь найти?" autocomplete="off" maxlength="100"><button type="button" data-search-close aria-label="Закрыть">✕</button></div><div id="searchSuggestions" class="search-suggestions"><div class="search-empty">Начни вводить название статьи или категорию</div></div><div class="search-bottom"><span>Enter — искать по всем статьям</span><span>ESC — закрыть</span></div></form></div></div></body></html>'''
    return head+body+footer

def crumb(*parts):
    return '<nav class="crumb" aria-label="Хлебные крошки"><a href="/">Главная</a>'+''.join('<span>›</span>'+(f'<a href="{E(url)}">{E(label)}</a>' if url else f'<b>{E(label)}</b>') for label,url in parts)+'</nav>'

def category_card(c):
    return f'''<a class="cat-card" href="/category/{E(c['slug'])}"><div class="cat-icon">{E(c['icon'])}</div><span class="cat-arrow">↗</span><h3>{E(c['title'])}</h3><p>{E(c['description'])}</p><div class="cat-bottom"><span>{int(c['article_count'])} статей</span><span>Открыть →</span></div></a>'''

def article_card(a,kind='card'):
    cat=a['category_title'] if 'category_title' in a.keys() else ''
    return f'''<a href="/article/{E(a['slug'])}" class="article-card {E(kind)}"><div class="article-icon">{E(a['category_icon'])}</div><div class="article-data"><span class="a-category">{E(cat)} <i>·</i> {E(a['difficulty'])}</span><h3>{E(a['title'])}</h3><p>{E(a['summary'])}</p><span class="article-meta">{date(a['updated_at'])} <b>•</b> {int(a['views'])} просмотров</span></div><span class="article-arrow">↗</span></a>'''

def homepage(categories, featured, latest, count, user=None):
    return base('Главная',f'''
<section class="hero"><div class="hero-bg"></div><div class="container hero-inner"><div class="hero-copy"><span class="eyebrow"><i></i> OFFICIAL KNOWLEDGE BASE <span class="eyebrow-line"></span> v1.0</span><h1>ТВОЯ ИСТОРИЯ.<br><span>ТВОИ ПРАВИЛА.</span></h1><p>Всё об игровом мире <strong>OBSIDIAN RUSSIA</strong> в одном месте. Изучай механики, находи ответы и открывай новые возможности.</p><form class="hero-search" action="/search"><label for="hero-query">⌕</label><input id="hero-query" name="q" placeholder="Поиск по знаниям, гайдам и каталогам..." maxlength="100" aria-label="Поиск"><button type="submit">НАЙТИ <span>↗</span></button></form><div class="hero-tags"><span>Часто ищут:</span><a href="/search?q=транспорт">транспорт</a><a href="/search?q=работа">работа</a><a href="/search?q=фракции">фракции</a><a href="/search?q=дом">недвижимость</a></div></div><div class="hero-visual"><div class="hero-logo"><img src="/static/ava.jpg" alt="OBSIDIAN RUSSIA"></div><span class="hero-visual-caption">ЗНАНИЕ — ТВОЯ СИЛА</span></div></div></section>
<section class="metrics"><div class="container metrics-inner"><div><b>{count}</b><span>СТАТЕЙ В БАЗЕ</span></div><div><b>{len(categories):02d}</b><span>КАТЕГОРИЙ</span></div><div><b>24/7</b><span>ДОСТУП К WIKI</span></div><div class="metric-cta">ВСЁ САМОЕ ВАЖНОЕ<br><strong>В ОДНОМ МЕСТЕ ↗</strong></div></div></section>
<section class="section container"><div class="section-heading"><div><span class="section-label">/ 01 — НАВИГАЦИЯ</span><h2>ИССЛЕДУЙ <em>МИР</em></h2><p>Выбери нужный раздел, чтобы быстро найти информацию.</p></div><a class="text-link" href="/categories">Все категории ↗</a></div><div class="categories-grid">{''.join(category_card(c) for c in categories)}</div></section>
<section class="catalog-spot container"><div class="catalog-spot-head"><span class="section-label">/ СПРАВОЧНИК ОБЪЕКТОВ</span><h2>КАТАЛОГ <em>ИГРЫ</em></h2><p>Транспорт, скины, недвижимость и игровые предметы — в одном каталоге.</p><a href="/catalog" class="button ghost">Открыть каталог ↗</a></div><div class="catalog-mini"><a href="/catalog/transport">🚘 <b>Транспорт</b> →</a><a href="/catalog/skins">🧍 <b>Скины</b> →</a><a href="/catalog/property">🏠 <b>Недвижимость</b> →</a></div></section>
<section class="section container section-featured"><div class="section-heading"><div><span class="section-label">/ 02 — РЕКОМЕНДУЕМ</span><h2>ПОПУЛЯРНЫЕ <em>ГАЙДЫ</em></h2><p>Начни с самых полезных материалов.</p></div><a class="text-link" href="/articles">Все статьи ↗</a></div><div class="article-grid">{''.join(article_card(a) for a in featured)}</div></section>
<section class="feature-banner"><div class="container feature-inner"><div class="feature-badge">OBSIDIAN / COMMUNITY</div><div><h2>СТАНЬ ЧАСТЬЮ <em>ИСТОРИИ</em></h2><p>Новости, обсуждения, обновления и ответы на вопросы — в официальных сообществах проекта.</p></div><div class="feature-buttons"><a href="{VK}" target="_blank" rel="noopener noreferrer" class="button primary">НАШ VK ↗</a><a href="{TG}" target="_blank" rel="noopener noreferrer" class="button ghost">TELEGRAM ↗</a></div></div></section>
<section class="section container"><div class="section-heading"><div><span class="section-label">/ 03 — НОВОЕ В БАЗЕ</span><h2>ПОСЛЕДНИЕ <em>ОБНОВЛЕНИЯ</em></h2><p>Актуальные дополнения и редакции статей.</p></div></div><div class="latest-list">{''.join(article_card(a,'compact') for a in latest)}</div></section>
<div class="container"><div class="notice-box"><span>ⓘ</span><p><strong>База знаний развивается вместе с проектом.</strong> Часть стартовых материалов является редакционной заготовкой, без неподтверждённых игровых цен, IP и характеристик.</p></div></div>''',categories,user,'home')

def category_index(cats,user=None):
    return base('Категории',f'<div class="container page-container">{crumb(("Категории",None))}<div class="page-intro"><span class="section-label">КАРТА ЗНАНИЙ</span><h1>ВСЕ <em>РАЗДЕЛЫ</em></h1><p>Выбери направление и изучи опубликованные материалы.</p></div><div class="categories-grid">{"".join(category_card(c) for c in cats)}</div></div>',cats,user,'catalog')

def category_page(c,articles,cats,user=None):
    return base(c['title'],f'<div class="container page-container">{crumb(("Категории","/categories"),(c["title"],None))}<div class="category-hero"><div class="category-symbol">{E(c["icon"])}</div><div><span class="section-label">РАЗДЕЛ БАЗЫ ЗНАНИЙ</span><h1>{E(c["title"])}</h1><p>{E(c["description"])}</p><span class="meta-tag">{len(articles)} материалов</span></div></div><div class="content-layout"><aside class="category-sidebar"><h4>КАТЕГОРИИ</h4>{nav(cats,c["slug"])}</aside><div class="list-content"><div class="list-header"><h2>Статьи раздела</h2><span>{len(articles)} материалов</span></div><div class="latest-list">{"".join(article_card(a,"compact") for a in articles) if articles else "<div class=empty>Пока здесь нет опубликованных статей.</div>"}</div></div></div></div>',cats,user,'catalog',c['description'])

def article_page(a,cats,related,user=None):
    headings=[m.group(1).strip() for m in re.finditer(r'^## (.+)$',a['content'],re.M)]
    toc=''.join(f'<a href="#section-{i}"><span>{i:02d}</span> {E(s)}</a>' for i,s in enumerate(headings,1))
    badge='<div class="sample-banner"><b>Редакционный материал</b> Статья содержит вводные сведения. Игровые значения уточняются командой проекта.</div>' if a['sample'] else ''
    img=f'<img class="article-cover" src="{E(a["image_path"])}" alt="{E(a["title"])}">' if a['image_path'] and a['image_path'].startswith(('/static/uploads/','/static/cover.jpg')) else ''
    body=f'''<div class="container page-container article-container">{crumb((a['category_title'],f'/category/{a["category_slug"]}'),(a['title'],None))}<div class="article-layout"><article class="article-main"><div class="article-head"><span class="section-label">{E(a['category_icon'])} {E(a['category_title']).upper()}</span><h1>{E(a['title'])}</h1><p>{E(a['summary'])}</p><div class="article-info"><span>◷ Обновлено: {date(a['updated_at'])}</span><span>◎ {int(a['views'])} просмотров</span><span>◈ {E(a['difficulty'])}</span></div></div>{badge}{img}<div class="prose">{md(a['content'])}</div><div class="article-after"><span>Была полезна статья? Поделись ей с друзьями.</span><button class="button ghost small" type="button" data-copy-url>Скопировать ссылку ↗</button></div><div class="article-rel"><h2>ЧИТАЙ <em>ТАКЖЕ</em></h2><div class="latest-list">{''.join(article_card(x,'compact') for x in related) if related else '<p>Другие материалы появятся позже.</p>'}</div></div></article><aside class="article-aside"><div class="toc"><h4>СОДЕРЖАНИЕ</h4>{toc if toc else '<p>Основная информация</p>'}<div class="toc-bottom"><a href="/category/{E(a['category_slug'])}">← Все статьи раздела</a></div></div><div class="side-social"><strong>OBSIDIAN RUSSIA</strong><p>Следи за обновлениями</p><a href="{TG}" target="_blank" rel="noopener noreferrer">Наш Telegram ↗</a></div></aside></div></div>'''
    return base(a['title'],body,cats,user,'articles',a['summary'])

def search_page(q,articles,cats,count,page=1,category='',title='Поиск по базе знаний'):
    cards=''.join(article_card(a,'compact') for a in articles)
    items=''.join(f'<option value="{E(c["slug"])}" {"selected" if c["slug"]==category else ""}>{E(c["title"])}</option>' for c in cats)
    nextlink=f'<a class="button ghost" href="/search?q={quote(q)}&category={quote(category)}&page={page+1}">Следующая страница →</a>' if count>page*15 else ''
    prevlink=f'<a class="button ghost" href="/search?q={quote(q)}&category={quote(category)}&page={page-1}">← Назад</a>' if page>1 else ''
    main=f'''<div class="container page-container">{crumb((title,None))}<div class="page-intro"><span class="section-label">НАЙДИ НУЖНУЮ ИНФОРМАЦИЮ</span><h1>{'РЕЗУЛЬТАТЫ <em>ПОИСКА</em>' if q else 'ВСЕ <em>СТАТЬИ</em>'}</h1><p>Доступно {count} материалов. Используй поиск и фильтр по разделам.</p></div><form class="filter-bar" action="/search" method="get"><input name="q" value="{E(q)}" placeholder="Название, тема, механика..." maxlength="100"><select name="category" aria-label="Раздел"><option value="">Все категории</option>{items}</select><button class="button primary" type="submit">НАЙТИ ↗</button></form><div class="content-layout"><aside class="category-sidebar"><h4>РАЗДЕЛЫ</h4>{nav(cats,category)}</aside><section class="list-content"><div class="list-header"><h2>{'По запросу: '+E(q) if q else 'Каталог статей'}</h2><span>{count} найдено</span></div><div class="latest-list">{cards if cards else '<div class="empty"><h3>Ничего не найдено</h3><p>Попробуй другой запрос или выбери иную категорию.</p><a href="/articles" class="button ghost">Все статьи</a></div>'}</div><div class="paging">{prevlink}{nextlink}</div></section></div></div>'''
    return main

def about(cats,user=None):
    return base('О Wiki',f'<div class="container page-container">{crumb(("О Wiki",None))}<div class="page-intro"><span class="section-label">О ПРОЕКТЕ</span><h1>ЗНАНИЯ <em>ОБЪЕДИНЯЮТ</em></h1><p>OBSIDIAN RUSSIA WIKI — база знаний игрового RolePlay-проекта.</p></div><div class="static-page"><h2>Для чего нужна Wiki?</h2><p>Здесь собраны инструкции, справочники и ответы на вопросы о мире OBSIDIAN RUSSIA. Мы развиваем разделы транспорта, профессий, организаций, недвижимости, бизнеса, предметов и игровых систем.</p><h2>Как поддерживается актуальность?</h2><p>Материалы редактируются через административную панель. Стартовые статьи отмечены как редакционные образцы, чтобы не выдавать неподтверждённые игровые характеристики за факты.</p><h2>Официальные контакты</h2><p>Новости проекта: <a href="{VK}">ВКонтакте</a> и <a href="{TG}">Telegram</a>.</p></div></div>',cats,user,'about')

def privacy(cats,user=None):
    return base('Конфиденциальность',f'<div class="container page-container">{crumb(("Конфиденциальность",None))}<div class="page-intro"><h1>КОНФИДЕНЦИАЛЬНОСТЬ</h1></div><div class="static-page"><p>Wiki использует технические cookie для авторизации редакторов. Для работы публичного поиска регистрация посетителей не требуется.</p><p>Для редакторов сохраняются логин, хеш пароля, сессии и история редакций. Технический сервер может вести журнал запросов. Сторонних аналитических и рекламных скриптов в сборке нет.</p><p>Перед публичным размещением администрация проекта должна дополнить данную политику сведениями о владельце, операторе данных, сроках хранения и контактах для обращений.</p></div></div>',cats,user)

def login(cats,csrf='',error=''):
    msg=f'<div class="form-error">{E(error)}</div>' if error else ''
    return base('Вход редактора',f'<div class="container login-wrap"><div class="login-card"><img src="/static/ava.jpg" alt=""><span class="section-label">ДОСТУП РЕДАКЦИИ</span><h1>ВХОД В <em>WIKI</em></h1><p>Панель управления материалами OBSIDIAN RUSSIA.</p>{msg}<form method="post" action="/login"><input type="hidden" name="csrf" value="{E(csrf)}"><label>Логин<input name="username" required minlength="3" maxlength="32" autocomplete="username"></label><label>Пароль<input name="password" type="password" required autocomplete="current-password"></label><button class="button primary block" type="submit">ВОЙТИ →</button></form><small>Доступ выдаётся администратором проекта.</small></div></div>',cats)

def admin_shell(content,user,cats,active='dashboard',flash=''):
    links=[('dashboard','/admin','Обзор'),('articles','/admin/articles','Статьи'),('catalog','/admin/catalog','Каталог'),('categories','/admin/categories','Категории'),('media','/admin/media','Медиафайлы'),('users','/admin/users','Редакторы'),('audit','/admin/audit','Журнал')]
    left=''.join(f'<a href="{href}" class="{"active" if k==active else ""}">{E(label)}</a>' for k,href,label in links if user['role']=='admin' or k not in ('users','audit'))
    note=f'<div class="flash">{E(flash)}</div>' if flash else ''
    shell=f'''<div class="container admin-layout"><aside class="admin-nav"><div class="admin-title">ПАНЕЛЬ WIKI</div>{left}<form action="/logout" method="post"><input type="hidden" name="csrf" value="{E(user['csrf'])}"><button type="submit">Выйти ↗</button></form></aside><div class="admin-content"><div class="admin-top"><span>Редактор: <b>{E(user['username'])}</b> · {E(user['role'])}</span><a href="/">Открыть Wiki ↗</a></div>{note}{content}</div></div>'''
    return base('Управление Wiki',shell,cats,user)

def admin_dashboard(stats,recent,user,cats,flash=''):
    cards=''.join(f'<div class="admin-stat"><b>{int(n)}</b><span>{E(t)}</span></div>' for t,n in stats)
    recentrows=''.join(f'<tr><td><a href="/admin/article/{a["id"]}">{E(a["title"])}</a></td><td>{E(a["status"])}</td><td>{date(a["updated_at"])}</td></tr>' for a in recent)
    return admin_shell(f'<div class="admin-header"><div><span class="section-label">CONTENT MANAGEMENT</span><h1>ПАНЕЛЬ <em>УПРАВЛЕНИЯ</em></h1></div><a class="button primary" href="/admin/article/new">+ Новая статья</a></div><div class="admin-stats">{cards}</div><div class="admin-card"><h2>Последние изменения</h2><div class="table-scroll"><table><thead><tr><th>Статья</th><th>Статус</th><th>Обновлено</th></tr></thead><tbody>{recentrows}</tbody></table></div></div><div class="notice-box"><span>ⓘ</span><p>В опубликованных статьях с пометкой «Редакционный материал» используются примерные общие описания. Обновите их на проверенные сведения о сервере перед публичным запуском.</p></div>',user,cats,flash=flash)

def admin_articles(rows,user,cats,flash=''):
    trs=''.join(f'<tr><td><a href="/admin/article/{a["id"]}"><strong>{E(a["title"])}</strong></a><small>/{E(a["slug"])}</small></td><td>{E(a["category_title"])}</td><td><span class="status {E(a["status"])}">{E(a["status"])}</span></td><td>{date(a["updated_at"])}</td><td><a class="simple-action" href="/admin/article/{a["id"]}">Изменить →</a></td></tr>' for a in rows)
    return admin_shell(f'<div class="admin-header"><h1>ВСЕ <em>СТАТЬИ</em></h1><a class="button primary" href="/admin/article/new">+ Новая статья</a></div><div class="admin-card"><div class="table-scroll"><table><thead><tr><th>Название</th><th>Раздел</th><th>Статус</th><th>Дата</th><th></th></tr></thead><tbody>{trs}</tbody></table></div></div>',user,cats,'articles',flash)

def admin_article_form(a,cats,user,history=(),flash=''):
    is_new=a is None
    val=lambda x:'' if is_new else E(a[x])
    options=''.join(f'<option value="{c["id"]}" {"selected" if not is_new and c["id"]==a["category_id"] else ""}>{E(c["title"])}</option>' for c in cats)
    checked=lambda k:'checked' if not is_new and a[k] else ''
    historyhtml=''.join(f'<div class="revision"><span>{date(r["saved_at"])} · {E(r["username"] or "система")}</span><form action="/admin/revision/{r["id"]}/restore" method="post" data-confirm="Восстановить редакцию? Текущая версия сохранится в истории."><input type="hidden" name="csrf" value="{E(user["csrf"])}"><button type="submit">Восстановить</button></form></div>' for r in history)
    return admin_shell(f'''<div class="admin-header"><div><span class="section-label">РЕДАКТОР</span><h1>{'НОВАЯ' if is_new else 'РЕДАКТИРОВАНИЕ'} <em>СТАТЬЯ</em></h1></div><a href="/admin/articles" class="button ghost">← К списку</a></div>
<form class="editor-form" action="/admin/article/{'new' if is_new else a['id']}" method="post"><input type="hidden" name="csrf" value="{E(user['csrf'])}"><div class="editor-main"><div class="admin-card"><div class="form-two"><label>Название<input name="title" required maxlength="130" value="{val('title')}" placeholder="Название статьи"></label><label>Адрес (slug)<input name="slug" required maxlength="100" pattern="[a-z0-9-]+" value="{val('slug')}" placeholder="name-of-article"></label></div><label>Краткое описание<textarea name="summary" rows="2" maxlength="300">{val('summary')}</textarea></label><label>Текст статьи (Markdown)<textarea name="content" id="editorContent" class="content-editor" rows="22" required maxlength="100000" placeholder="# Заголовок&#10;&#10;## Раздел&#10;&#10;- Пункт списка">{val('content')}</textarea></label><div class="editor-tips"><b>Поддерживается:</b> # заголовок · ## подзаголовок · **жирный** · - список · &gt; заметка · [текст](https://адрес)</div></div></div><aside class="editor-aside"><div class="admin-card"><h3>Публикация</h3><label>Раздел<select name="category_id">{options}</select></label><label>Тип материала<select name="difficulty">{''.join(f'<option value="{E(k)}" {"selected" if not is_new and a["difficulty"]==k else ""}>{E(k)}</option>' for k in ("Новичкам","Справочник","Важно","Продвинутым"))}</select></label><label>Статус<select name="status"><option value="published" {'' if not is_new and a['status']=='draft' else 'selected'}>Опубликовано</option><option value="draft" {'selected' if not is_new and a['status']=='draft' else ''}>Черновик</option></select></label><label>Обложка (путь из Медиа)<input name="image_path" value="{val('image_path')}" maxlength="250" placeholder="/static/uploads/..." id="coverPath"></label><label class="checkline"><input type="checkbox" name="featured" value="1" {checked('featured')}> Рекомендуемая статья</label><label class="checkline"><input type="checkbox" name="sample" value="1" {checked('sample')}> Показать пометку «Редакционный материал»</label><button class="button primary block" type="submit">СОХРАНИТЬ СТАТЬЮ</button>{f'<a class="button ghost block" href="/article/{E(a["slug"])}">Просмотр ↗</a>' if not is_new and a['status']=='published' else ''}</div></aside></form>
{f'<div class="admin-card revisions"><h2>История редакций</h2>{historyhtml or "<p>Предыдущих редакций нет.</p>"}</div>' if not is_new else ''}''',user,cats,'articles',flash)

def admin_categories(cats,user,flash=''):
    rows=''.join(f'''<form class="category-edit" action="/admin/category/{c["id"]}" method="post"><input type="hidden" name="csrf" value="{E(user["csrf"])}"><input name="icon" aria-label="Иконка" value="{E(c["icon"])}" maxlength="8"><input name="title" aria-label="Название" value="{E(c["title"])}" required maxlength="80"><input name="slug" aria-label="Адрес" value="{E(c["slug"])}" required maxlength="60" pattern="[a-z0-9-]+"><input name="description" aria-label="Описание" value="{E(c["description"])}" maxlength="200"><input type="number" name="sort_order" aria-label="Порядок" value="{int(c["sort_order"])}" min="0" max="999"><button class="button ghost small">Сохранить</button></form>''' for c in cats)
    return admin_shell(f'''<div class="admin-header"><h1>КАТЕГОРИИ <em>WIKI</em></h1></div><div class="admin-card"><h2>Редактирование категорий</h2><p>Название, адрес и порядок отображения разделов.</p>{rows}</div><div class="admin-card"><h2>Новая категория</h2><form class="form-two" method="post" action="/admin/category/new"><input type="hidden" name="csrf" value="{E(user['csrf'])}"><label>Название<input name="title" required maxlength="80"></label><label>Slug<input name="slug" required pattern="[a-z0-9-]+" maxlength="60"></label><label>Описание<input name="description" maxlength="200"></label><label>Иконка<input name="icon" value="📖" maxlength="8"></label><button class="button primary">Добавить категорию</button></form></div>''',user,cats,'categories',flash)

def admin_media(rows,user,cats,flash=''):
    cells=''.join(f'<div class="media-card"><img src="{E(r["path"])}" alt=""><b>{E(r["name"])}</b><input readonly value="{E(r["path"])}" aria-label="Путь файла"><button class="button ghost small" type="button" data-copy="{E(r["path"])}">Копировать путь</button></div>' for r in rows)
    return admin_shell(f'''<div class="admin-header"><h1>МЕДИА<em>ФАЙЛЫ</em></h1></div><div class="admin-card"><h2>Загрузить изображение</h2><form action="/admin/upload" method="post" enctype="multipart/form-data" class="upload-form"><input type="hidden" name="csrf" value="{E(user['csrf'])}"><input type="file" name="image" required accept="image/jpeg,image/png,image/webp"><button class="button primary">Загрузить</button></form><p>JPEG, PNG или WebP · до 3 МБ. SVG и исполняемые файлы не допускаются.</p></div><div class="media-grid">{cells if cells else '<p>Файлов ещё нет. Загрузите первую иллюстрацию.</p>'}</div>''',user,cats,'media',flash)

def admin_users(rows,user,cats,flash=''):
    trs=''.join(f'<tr><td>{E(r["username"])}</td><td>{E(r["role"])}</td><td>{date(r["created_at"])}</td></tr>' for r in rows)
    return admin_shell(f'''<div class="admin-header"><h1>КОМАНДА <em>WIKI</em></h1></div><div class="admin-card"><h2>Редакторы</h2><table><tr><th>Логин</th><th>Роль</th><th>Создан</th></tr>{trs}</table></div><div class="admin-card"><h2>Добавить редактора</h2><form class="form-two" action="/admin/users" method="post"><input type="hidden" name="csrf" value="{E(user['csrf'])}"><label>Логин<input name="username" minlength="3" maxlength="32" required pattern="[A-Za-z0-9_-]+"></label><label>Пароль (минимум 12 символов)<input type="password" name="password" minlength="12" required></label><label>Роль<select name="role"><option value="editor">Редактор</option><option value="admin">Администратор</option></select></label><button class="button primary">Создать аккаунт</button></form></div>''',user,cats,'users',flash)

def admin_audit(rows,user,cats):
    trs=''.join(f'<tr><td>{date(r["created_at"])}</td><td>{E(r["username"] or "система")}</td><td>{E(r["action"])}</td><td>{E(r["target"])}</td></tr>' for r in rows)
    return admin_shell(f'<div class="admin-header"><h1>ЖУРНАЛ <em>ДЕЙСТВИЙ</em></h1></div><div class="admin-card"><table><tr><th>Дата</th><th>Автор</th><th>Действие</th><th>Объект</th></tr>{trs}</table></div>',user,cats,'audit')

def notfound(cats,user=None,status=404,detail='Запрошенная страница не найдена.'):
    return base('Страница не найдена',f'<div class="container error-page"><b>{status}</b><h1>ТУТ ПОКА <em>ПУСТО</em></h1><p>{E(detail)}</p><a class="button primary" href="/">На главную ↗</a></div>',cats,user)

# Structured catalog pages; product-specific facts are supplied by wiki editors.
def catalog_index(types, counts, cats, user=None):
    cards=''.join(f'<a class="catalog-type" href="/catalog/{E(kind)}"><span>{E(icon)}</span><h3>{E(title)}</h3><p>{E(desc)}</p><small>{int(counts.get(kind,0))} карточек <b>→</b></small></a>' for kind,title,desc,icon in types)
    content=f'<div class="container page-container">{crumb(("Каталог",None))}<div class="page-intro"><span class="section-label">ОБЪЕКТЫ ИГРОВОГО МИРА</span><h1>КАТАЛОГ <em>OBSIDIAN</em></h1><p>Транспорт, скины, недвижимость и игровые объекты. Информация добавляется по мере подтверждения механик.</p></div><div class="catalog-types">{cards}</div></div>'
    return base('Каталог игры',content,cats,user,'catalog')

def catalog_kind(kind,kindname,desc,icon,items,tiers,q,selected_tier,cats,user=None):
    opts=''.join(f'<option value="{E(t)}" {"selected" if t==selected_tier else ""}>{E(t)}</option>' for t in tiers)
    cards=''.join(catalog_card(a,icon) for a in items)
    empty='<div class="empty"><h3>Каталог пополняется</h3><p>Пока нет подтверждённых карточек для выбранных условий. Администрация сможет добавить объекты в панели Wiki.</p><a class="button ghost" href="/catalog">К каталогам</a></div>'
    content=f'''<div class="container page-container">{crumb(("Каталог","/catalog"),(kindname,None))}<div class="category-hero"><div class="category-symbol">{E(icon)}</div><div><span class="section-label">КАТАЛОГ ИГРЫ</span><h1>{E(kindname)}</h1><p>{E(desc)}</p></div></div><form class="filter-bar" action="/catalog/{E(kind)}"><input name="q" maxlength="100" value="{E(q)}" placeholder="Поиск по названию и характеристикам"><select name="tier" aria-label="Класс"><option value="">Все классы</option>{opts}</select><button class="button primary">Показать ↗</button></form><div class="catalog-list">{cards if cards else empty}</div></div>'''
    return base(kindname,content,cats,user,'catalog',desc)

def catalog_card(a,icon):
    path=a['image_path']
    cover=f'<img src="{E(path)}" alt="{E(a["title"])}">' if path.startswith(('/static/uploads/','/static/cover.jpg')) else f'<div class="catalog-placeholder">{E(icon)}</div>'
    return f'<a href="/catalog/item/{E(a["slug"])}" class="catalog-item"><div class="catalog-img">{cover}</div><div class="catalog-description"><span class="section-label">{E(a["tier"] or "СПРАВОЧНИК")}</span><h3>{E(a["title"])}</h3><p>{E(a["summary"])}</p><span>Подробнее ↗</span></div></a>'

def catalog_item(a,kindname,icon,cats,user=None):
    parameters=[]
    for line in a['parameters'].splitlines():
        if ':' in line:
            key,val=line.split(':',1)
            if key.strip() and val.strip():parameters.append((key.strip(),val.strip()))
    rows=''.join(f'<div><span>{E(k)}</span><b>{E(val)}</b></div>' for k,val in parameters[:30])
    path=a['image_path']
    img=f'<img src="{E(path)}" alt="{E(a["title"])}">' if path.startswith(('/static/uploads/','/static/cover.jpg')) else f'<span>{E(icon)}</span>'
    sample='<div class="sample-banner">Карточка-пример. Сведения требуют подтверждения командой проекта.</div>' if a['sample'] else ''
    tier=f'<div><span>Класс / тип</span><b>{E(a["tier"])}</b></div>' if a['tier'] else ''
    price=f'<div><span>Стоимость</span><b>{E(a["price_text"])}</b></div>' if a['price_text'] else ''
    content=f'''<div class="container page-container">{crumb(("Каталог","/catalog"),(kindname,f'/catalog/{a["kind"]}'),(a['title'],None))}<div class="catalog-detail"><div class="catalog-detail-visual">{img}</div><div class="catalog-detail-data"><span class="section-label">{E(kindname).upper()}</span><h1>{E(a['title'])}</h1><p>{E(a['summary'])}</p>{sample}<div class="catalog-params">{tier}{price}{rows}</div><a href="/catalog/{E(a['kind'])}" class="button ghost">← К списку</a></div></div></div>'''
    return base(a['title'],content,cats,user,'catalog',a['summary'])

def admin_catalog(items,user,cats,flash=''):
    rows=''.join(f'<tr><td><a href="/admin/catalog/item/{a["id"]}">{E(a["title"])}</a></td><td>{E(a["kind"])}</td><td><span class="status {E(a["status"])}">{E(a["status"])}</span></td><td>{date(a["updated_at"])}</td><td><a href="/admin/catalog/item/{a["id"]}" class="simple-action">Изменить →</a></td></tr>' for a in items)
    inner=f'<div class="admin-header"><h1>КАТАЛОГ <em>ОБЪЕКТОВ</em></h1><a href="/admin/catalog/new" class="button primary">+ Карточка</a></div><div class="admin-card"><p>Создавайте карточки транспорта, скинов, имущества, работ и предметов. Не публикуйте неподтверждённые игровые цены и параметры.</p><div class="table-scroll"><table><tr><th>Объект</th><th>Тип</th><th>Статус</th><th>Обновлён</th><th></th></tr>{rows}</table></div></div>'
    return admin_shell(inner,user,cats,'catalog',flash)

def admin_catalog_editor(a,types,user,cats,flash=''):
    isnew=a is None
    value=lambda k:'' if isnew else E(a[k])
    options=''.join(f'<option value="{E(kind)}" {"selected" if not isnew and a["kind"]==kind else ""}>{E(title)}</option>' for kind,title,_,_ in types)
    check=lambda k:'checked' if not isnew and a[k] else ''
    action='/admin/catalog/new' if isnew else '/admin/catalog/item/'+str(a['id'])
    selected_draft='selected' if isnew or a['status']=='draft' else ''
    selected_pub='selected' if not isnew and a['status']=='published' else ''
    inner=f'''<div class="admin-header"><h1>{'НОВАЯ' if isnew else 'ИЗМЕНИТЬ'} <em>КАРТОЧКА</em></h1><a href="/admin/catalog" class="button ghost">← К каталогу</a></div><form class="editor-form" method="post" action="{action}"><input type="hidden" name="csrf" value="{E(user['csrf'])}"><div class="admin-card"><div class="form-two"><label>Название<input name="title" value="{value('title')}" maxlength="130" required></label><label>Slug<input name="slug" value="{value('slug')}" pattern="[a-z0-9-]+" maxlength="100" required></label></div><label>Описание<textarea name="summary" rows="4" maxlength="500">{value('summary')}</textarea></label><div class="form-two"><label>Класс / тип<input name="tier" value="{value('tier')}" maxlength="80" placeholder="Например: седан"></label><label>Цена (только подтверждённая)<input name="price_text" value="{value('price_text')}" maxlength="100"></label></div><label>Характеристики (по одной в строке: ключ: значение)<textarea name="parameters" rows="10" maxlength="5000" placeholder="Производитель: ...&#10;Мест: ...">{value('parameters')}</textarea></label></div><aside class="admin-card"><h3>Публикация</h3><label>Каталог<select name="kind">{options}</select></label><label>Статус<select name="status"><option value="draft" {selected_draft}>Черновик</option><option value="published" {selected_pub}>Опубликовано</option></select></label><label>Обложка (из Медиа)<input name="image_path" value="{value('image_path')}" maxlength="250"></label><label class="checkline"><input type="checkbox" name="sample" value="1" {check('sample')}> Карточка-пример</label><button class="button primary block">Сохранить</button></aside></form>'''
    return admin_shell(inner,user,cats,'catalog',flash)
