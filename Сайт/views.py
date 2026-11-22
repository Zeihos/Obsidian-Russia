"""HTML views. All user-controlled strings are escaped before interpolation."""
import html, datetime, re
from urllib.parse import quote
from db import now

def E(x): return html.escape(str(x if x is not None else ''),quote=True)

def short(s,n=140):
    t=str(s or '').strip()
    return t if len(t)<=n else t[:n-1].rstrip()+'…'

def date(s):
    try: return datetime.datetime.fromisoformat(s).strftime('%d.%m.%Y')
    except (TypeError,ValueError):return '—'

def icon(name,size=20):
    paths={
        'arrow':'<path d="M5 12h14m-7-7 7 7-7 7"/>',
        'up':'<path d="M7 17 17 7M7 7h10v10"/>',
        'play':'<path d="m8 5 12 7-12 7V5Z"/>',
        'game':'<rect x="2" y="7" width="20" height="11" rx="5"/><path d="M7 11v5m-2.5-2.5h5M16 12h.01M19 15h.01"/>',
        'users':'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
        'flash':'<path d="m13 2-3 8H4l7 12 3-8h6L13 2Z"/>',
        'shield':'<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/>',
        'world':'<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20M12 2a15 15 0 0 0 0 20"/>',
        'check':'<path d="m4 12 5 5L20 6"/>',
        'clock':'<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
        'server':'<rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01M6 17h.01"/>',
        'news':'<path d="M4 19V4h16v15a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2Z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
        'user':'<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
        'coins':'<circle cx="12" cy="12" r="9"/><path d="M12 6v12M15.5 9.5c-1.3-2-6.4-2-7 0-.7 2 6.1 2 7 4 0 1.5-1.6 2.5-4 2.5"/>',
        'download':'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
        'menu':'<path d="M4 6h16M4 12h16M4 18h16"/>',
        'close':'<path d="M18 6 6 18M6 6l12 12"/>',
        'logout':'<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 4 5 5-5 5m5-5H9"/>',
        'gear':'<circle cx="12" cy="12" r="3"/><path d="M19 13a7 7 0 0 0 0-2l2-1-2-4-2 1a7 7 0 0 0-2-1l-1-3h-4L9 6a7 7 0 0 0-2 1L5 6l-2 4 2 1a7 7 0 0 0 0 2l-2 1 2 4 2-1a7 7 0 0 0 2 1l1 3h4l1-3a7 7 0 0 0 2-1l2 1 2-4-2-1Z"/>',
        'ticket':'<path d="M3 8V5h18v3a4 4 0 0 0 0 8v3H3v-3a4 4 0 0 0 0-8Z"/><path d="M13 5v14"/>',
        'bell':'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
        'key':'<circle cx="8" cy="15" r="4"/><path d="m11 12 9-9 1 4-3 1v3h-3v3h-3"/>',
        'mail':'<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2 6 10 7 10-7"/>',
        'back':'<path d="M19 12H5m7 7-7-7 7-7"/>',
        'star':'<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.9L12 18l-6.2 3.1L7 14.2 2 9.3l6.9-1L12 2Z"/>',
        'heart':'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
    }
    return f'<svg class="ico" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths.get(name,paths["arrow"])}</svg>'

def link(url,txt,cls=''):
    return f'<a class="{cls}" href="{E(url)}">{txt}</a>' if url else f'<span class="{cls} is-disabled" aria-disabled="true">{txt}</span>'

def badge(text,cls='muted'):
    return f'<span class="pill pill-{E(cls)}">{E(text)}</span>'

def csrf_field(csrf):return f'<input type="hidden" name="csrf" value="{E(csrf)}">'

def layout(title,body,path='/',user=None,settings=None,csrf='',notice='',description='OBSIDIAN RUSSIA — новый игровой RolePlay-проект.', og_type='website'):
    settings=settings or {}
    brand='OBSIDIAN RUSSIA'
    nav=[('/', 'Главная'),('/play','Начать играть'),('/servers','Серверы'),('/news','Новости'),('/donate','Магазин'),('/about','О проекте')]
    links=''.join(f'<a href="{u}" class="{"active" if path==u or (u=="/news" and path.startswith("/news/")) else ""}">{t}</a>' for u,t in nav)
    userbtn=(f'<a class="nav-account" href="/account">{icon("user",17)} <span>{E(user["username"])}</span></a>' if user else f'<a class="nav-account" href="/login">{icon("user",17)} <span>Личный кабинет</span></a>')
    vk=settings.get('vk','https://vk.ru/obsidian_brussia');tg=settings.get('telegram','https://t.me/obsidian_brussia');forum=settings.get('forum','')
    social=''.join(link(u,k,'social-link') for u,k in ((vk,'VK'),(tg,'TG'))) 
    if forum:social+=link(forum,'ФОРУМ','social-link')
    noticehtml=f'<div class="flash" role="status">{icon("check",19)} {E(notice)}</div>' if notice else ''
    return f'''<!doctype html><html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{E(title)} — OBSIDIAN RUSSIA</title><meta name="description" content="{E(description)}">
<meta property="og:type" content="{E(og_type)}"><meta property="og:title" content="{E(title)} — OBSIDIAN RUSSIA"><meta property="og:description" content="{E(description)}"><meta property="og:image" content="/static/cover.jpg">
<meta name="theme-color" content="#0d0a0b"><link rel="icon" href="/static/favicon.png" type="image/png">
<link rel="stylesheet" href="/static/style.css"><script src="/static/app.js" defer></script>
</head><body><div class="noise" aria-hidden="true"></div>
<header class="site-header"><div class="shell header-inner">
<a class="brand" href="/" aria-label="OBSIDIAN RUSSIA — главная"><img src="/static/favicon.png" width="46" height="46" alt=""><span class="brand-name">OBSIDIAN <b>RUSSIA</b><small>ИГРОВОЙ ПРОЕКТ</small></span></a>
<nav class="desktop-nav" aria-label="Основная навигация">{links}</nav>
<div class="header-actions">{userbtn}<button id="menu-toggle" class="menu-toggle" type="button" aria-label="Открыть меню" aria-expanded="false">{icon('menu',23)}</button></div>
</div><div class="mobile-nav" id="mobile-nav" hidden><nav aria-label="Мобильная навигация">{links}{userbtn}</nav></div></header>
{noticehtml}
<main id="main">{body}</main>
<footer class="site-footer"><div class="shell footer-main"><div class="footer-brand"><a class="brand" href="/"><img src="/static/favicon.png" width="53" height="53" alt=""><span class="brand-name">OBSIDIAN <b>RUSSIA</b><small>ТВОЯ ИСТОРИЯ. ТВОИ ПРАВИЛА.</small></span></a><p>Собственный RolePlay-мир. Проект находится в разработке: мы публикуем только подтверждённую информацию о запуске.</p></div>
<div class="footer-col"><h4>Проект</h4><a href="/about">О нас</a><a href="/servers">Серверы</a><a href="/news">Новости</a><a href="/play">Как играть</a></div>
<div class="footer-col"><h4>Информация</h4><a href="/rules">Правила сайта</a><a href="/privacy">Политика конфиденциальности</a><a href="/contact">Поддержка</a></div>
<div class="footer-col"><h4>Сообщества</h4><div class="footer-social">{social}</div><p>Будь в курсе обновлений и анонсов проекта.</p></div>
</div><div class="shell footer-bottom"><span>© {datetime.datetime.now().year} OBSIDIAN RUSSIA. Независимый игровой проект.</span><span>Создано с характером <b>◆</b></span></div></footer>
</body></html>'''

def head(kicker,title,desc='',eyebrow=True):
    return f'<div class="page-intro shell"><div class="kicker">{icon("star",15)} {E(kicker)}</div><h1>{title}</h1><p>{E(desc)}</p></div>'

def section_title(tag,title,desc='',more=None):
    return f'<div class="section-head"><div><div class="kicker">{E(tag)}</div><h2>{title}</h2><p>{E(desc)}</p></div>{f"<a class=\"text-link\" href=\"{E(more)}\">Смотреть всё {icon('arrow',17)}</a>" if more else ""}</div>'

def news_card(n):
    cat=E(n['category']); nm=E(n['title']); preview=E(short(n['excerpt'],142))
    return f'''<a class="news-card panel" href="/news/{int(n['id'])}"><div class="news-art"><div class="news-art-glow"></div><img src="/static/avatar.jpg" loading="lazy" alt=""><span class="news-category">{cat}</span></div><div class="news-copy"><span class="news-date">{date(n['created_at'])}</span><h3>{nm}</h3><p>{preview}</p><span class="news-more">Подробнее {icon('arrow',16)}</span></div></a>'''

def server_card(s):
    status=s['status']
    statuslabel={'online':'Работает','offline':'Недоступен','soon':'Скоро запуск'}[status]
    statusclass={'online':'live','offline':'off','soon':'soon'}[status]
    addr=E(s['address']) if s['address'] else 'Адрес будет опубликован'
    online=(f'<strong>{int(s["online"])} <small>/ {int(s["capacity"])} игроков</small></strong>' if status=='online' and s['capacity'] else '<strong>Ожидаем запуск</strong>' if status=='soon' else '<strong>Нет данных</strong>')
    return f'''<article class="server-card panel"><div class="server-top"><div class="server-symbol">{icon("server",27)}</div><span class="status status-{statusclass}"><i></i>{statuslabel}</span></div><h3>{E(s['name'])}</h3><p>{E(s['description'])}</p><div class="server-meter">{online}<div class="meter"><span class="meter-fill" style="width:{min(100,max(0,round((s['online']/s['capacity'])*100))) if s['capacity'] and status=='online' else 0}%"></span></div></div><div class="server-foot"><span>{addr}</span><a href="/play">Как начать {icon('arrow',17)}</a></div></article>'''

def home(c,settings):
    news=c.execute('SELECT * FROM news WHERE published=1 ORDER BY created_at DESC,id DESC LIMIT 3').fetchall()
    servers=c.execute('SELECT * FROM servers ORDER BY id LIMIT 3').fetchall()
    n=c.execute('SELECT COUNT(*) FROM news WHERE published=1').fetchone()[0]
    notice=E(settings.get('site_notice',''))
    hero=f'''<section class="home-hero"><div class="hero-backdrop"></div><div class="shell hero-layout"><div class="hero-copy"><div class="hero-label"><span class="live-dot"></span> НОВАЯ ЭПОХА ROLEPLAY</div><h1>ТВОЙ ГОРОД.<br><span>ТВОЯ ИСТОРИЯ.</span></h1><p>От первого шага до собственной легенды. Знакомься с OBSIDIAN RUSSIA — будущим миром, в котором всё решают твои действия.</p><div class="hero-buttons"><a class="btn btn-primary" href="/play">{icon('play',18)} Начать путешествие {icon('arrow',19)}</a><a class="btn btn-ghost" href="/about">Узнать о проекте</a></div><div class="hero-note"><span class="note-line"></span><span>В разработке · Следи за анонсами</span></div></div><div class="hero-logo"><img src="/static/avatar.jpg" alt="Фирменный знак OBSIDIAN RUSSIA" loading="eager"></div></div><div class="hero-bottom shell"><span>ОТКРОЙ СВОЮ ИСТОРИЮ</span><span class="hero-scroll">ЛИСТАЙ ВНИЗ <span>↓</span></span></div></section>'''
    noticebox=f'<div class="shell"><div class="announcement"><div class="announcement-icon">{icon("bell",21)}</div><div><strong>СТАТУС ПРОЕКТА</strong><p>{notice}</p></div><a href="/news">Новости {icon("arrow",18)}</a></div></div>' if notice else ''
    features=[('01','ЖИВОЙ МИР','Город, где важна каждая встреча. Создавай свою историю и становись частью сообщества.','world'),('02','ТВОЙ ПУТЬ','Выбирай направление развития: карьера, бизнес, команда или собственные цели.','flash'),('03','ИГРА С ДРУЗЬЯМИ','Объединяйтесь, общайтесь и открывайте новые возможности вместе.','users'),('04','СВОИ ПРАВИЛА','Продуманное RolePlay-взаимодействие, честное развитие и уважение к другим игрокам.','shield')]
    feats=''.join(f'<div class="feature"><div class="feature-id">{i}</div><div class="feature-icon">{icon(ic,25)}</div><h3>{ttl}</h3><p>{ds}</p></div>' for i,ttl,ds,ic in features)
    about=f'''<section class="section section-concept"><div class="shell"><div class="split"><div class="split-content"><div class="kicker">О НАШЕМ МИРЕ</div><h2>НЕ ПРОСТО ИГРА.<br><em>ТВОЯ РЕАЛЬНОСТЬ.</em></h2><p>OBSIDIAN RUSSIA создаётся как пространство для ярких RolePlay-историй. Мы прорабатываем атмосферу, удобство и возможности взаимодействия игроков.</p><p>Важное правило: до анонса запуска задуманные механики не считаются готовыми функциями.</p><a class="btn btn-outline" href="/about">Подробнее о проекте {icon('arrow',18)}</a></div><div class="split-visual"><img src="/static/cover.jpg" loading="lazy" alt="Фирменная обложка OBSIDIAN RUSSIA"><div class="split-watermark">OBSIDIAN</div></div></div></div></section>'''
    scontent=''.join(server_card(s) for s in servers)
    ncontent=''.join(news_card(x) for x in news)
    return (hero+noticebox+f'''<section class="section features-section"><div class="shell">{section_title('ОСНОВА ПРОЕКТА','ЧТО ТЕБЯ ЖДЁТ','Наша концепция игрового мира — в четырёх принципах.')}<div class="features-grid">{feats}</div></div></section>'''+about+
      f'''<section class="section"><div class="shell">{section_title('ИГРОВЫЕ МИРЫ','НАШИ СЕРВЕРЫ','Сведения о доступности обновляются администрацией.',more='/servers')}<div class="server-grid">{scontent}</div></div></section>'''+
      f'''<section class="section news-section"><div class="shell">{section_title('В ЦЕНТРЕ СОБЫТИЙ','ПОСЛЕДНИЕ НОВОСТИ','Анонсы, планы и важные изменения проекта.',more='/news')}<div class="news-grid">{ncontent or '<p class="muted">Пока нет опубликованных новостей.</p>'}</div></div></section>'''+
      f'''<section class="section"><div class="shell"><div class="cta"><div class="cta-shape"></div><div class="kicker">БУДЬ ПЕРВЫМ</div><h2>ИСТОРИЯ НАЧИНАЕТСЯ<br><span>С ТЕБЯ.</span></h2><p>Подпишись на наши сообщества, чтобы первым узнать о запуске.</p><div class="cta-actions"><a class="btn btn-primary" href="{E(settings.get('vk'))}" target="_blank" rel="noopener noreferrer">Сообщество VK {icon('up',17)}</a><a class="btn btn-ghost" href="{E(settings.get('telegram'))}" target="_blank" rel="noopener noreferrer">Наш Telegram {icon('up',17)}</a></div></div></div></section>''')

def servers_page(c):
    rows=c.execute('SELECT * FROM servers ORDER BY id').fetchall()
    return head('СТАТУС СЕРВЕРОВ','ИГРОВЫЕ <span>МИРЫ</span>','Выбирай сервер и следи за статусом запуска.')+f'<section class="section compact"><div class="shell"><div class="server-grid">{"".join(server_card(r) for r in rows)}</div><p class="small-note">Статусы обновляются администрацией. Онлайн не является автоматическим мониторингом игры, пока не подключён источник игровых данных.</p></div></section>'

def play_page(settings):
    steps=[('01','УЗНАЙ О ЗАПУСКЕ','Следи за сообщениями в наших официальных сообществах.'),('02','СКАЧАЙ КЛИЕНТ','После публикации официального клиента скачай его по ссылке на этой странице.'),('03','ВЫБЕРИ СЕРВЕР','Открой список игровых миров и выбери доступный сервер.'),('04','НАЧНИ ИСТОРИЮ','Создай персонажа и познакомься с правилами RolePlay.')]
    cards=''.join(f'<article class="step panel"><span>{i}</span><h3>{n}</h3><p>{d}</p></article>' for i,n,d in steps)
    links=''
    for key,caption,system in [('android_download','Скачать для Android','ANDROID'),('windows_download','Скачать для Windows','WINDOWS')]:
        url=settings.get(key,'')
        if url: links+=f'<a class="download-item" href="{E(url)}" rel="noopener noreferrer" target="_blank"><div>{icon("download",23)} <span>{system}<strong>{caption}</strong></span></div>{icon("arrow",20)}</a>'
        else:links+=f'<div class="download-item inactive"><div>{icon("clock",23)} <span>{system}<strong>Скоро будет доступно</strong></span></div><span class="coming-soon">ОЖИДАЕМ РЕЛИЗ</span></div>'
    return head('СТАРТ ИГРЫ','НАЧНИ <span>ИГРАТЬ</span>','Всё, что нужно знать перед первым входом в OBSIDIAN RUSSIA.')+f'''<section class="section compact"><div class="shell">{section_title('ПОШАГОВО','ЧЕТЫРЕ ШАГА ДО ИГРЫ','Короткий маршрут от знакомства до входа на сервер.')}<div class="steps-grid">{cards}</div><div class="download-panel panel"><div><div class="kicker">УСТАНОВКА</div><h2>ИГРОВОЙ КЛИЕНТ</h2><p>Здесь появятся только подтверждённые ссылки на официальные установщики OBSIDIAN RUSSIA. Не скачивай неизвестные APK от имени проекта.</p></div><div class="download-links">{links}</div></div></div></section>'''

def news_page(c):
    news=c.execute('SELECT * FROM news WHERE published=1 ORDER BY created_at DESC,id DESC').fetchall()
    return head('СОБЫТИЯ И АНОНСЫ','НАШИ <span>НОВОСТИ</span>','Все важные события OBSIDIAN RUSSIA в одном месте.')+f'<section class="section compact"><div class="shell"><div class="news-grid">{"".join(news_card(n) for n in news) or "<p>Публикации скоро появятся.</p>"}</div></div></section>'

def article_page(n):
    txt=''.join(f'<p>{E(p.strip()).replace(chr(10),"<br>")}</p>' for p in n['body'].split('\n\n') if p.strip())
    return f'''<section class="section article-section"><div class="shell article-wrap"><a href="/news" class="text-link">{icon('back',17)} Ко всем новостям</a><div class="article-top"><div class="kicker">{E(n['category'])} / {date(n['created_at'])}</div><h1>{E(n['title'])}</h1><p>{E(n['excerpt'])}</p></div><div class="article-image"><img src="/static/cover.jpg" alt="OBSIDIAN RUSSIA"></div><article class="article-content">{txt}</article><a class="btn btn-outline" href="/news">{icon('back',18)} Назад к новостям</a></div></section>'''

def donate_page(settings):
    url=settings.get('donation_url','')
    content=(f'<a class="btn btn-primary" href="{E(url)}" target="_blank" rel="noopener noreferrer">Перейти в официальный магазин {icon("up",18)}</a><p class="small-note">Оплата проводится только через указанный администрацией внешний сервис. Сайт не хранит платёжные данные.</p>' if url else f'<span class="pill pill-muted">{icon("clock",15)} ПОКА НЕДОСТУПНО</span><p>Мы подключим официальный магазин после настройки безопасной платёжной системы. Покупки и начисления здесь пока не производятся.</p>')
    return head('ПОДДЕРЖКА ПРОЕКТА','ИГРОВОЙ <span>МАГАЗИН</span>','Официальные покупки будут доступны после запуска платёжной инфраструктуры.')+f'''<section class="section compact"><div class="shell"><div class="shop-layout"><div class="shop-art"><img src="/static/avatar.jpg" alt="Логотип OBSIDIAN RUSSIA"></div><div class="shop-info"><div class="kicker">ОФИЦИАЛЬНЫЙ МАГАЗИН</div><h2>ПОДДЕРЖИ<br><span>СВОЙ МИР</span></h2><p>Будущие дополнительные возможности, игровые предложения и поддержка проекта будут доступны исключительно через официальный платёжный канал.</p>{content}</div></div><div class="disclaimer">{icon('shield',20)} Никогда не отправляй деньги на реквизиты из личных сообщений. Все официальные ссылки будут опубликованы здесь и в наших сообществах.</div></div></section>'''

def about_page(settings):
    return head('НАША ФИЛОСОФИЯ','КТО МЫ <span>ТАКИЕ?</span>','OBSIDIAN RUSSIA — новый самостоятельный проект с собственной идентичностью.')+f'''<section class="section compact"><div class="shell"><div class="about-banner"><img src="/static/cover.jpg" alt="Официальная обложка OBSIDIAN RUSSIA"></div><div class="about-columns"><div><div class="kicker">ИДЕЯ</div><h2>СОЗДАЁМ МИР,<br>В КОТОРЫЙ ХОЧЕТСЯ ВЕРНУТЬСЯ.</h2></div><div><p>OBSIDIAN RUSSIA — развивающийся RolePlay-проект. Мы хотим объединить атмосферу города, социальное взаимодействие и свободу создавать собственные игровые истории.</p><p>Оформление проекта построено вокруг образа медведя, ночного мегаполиса, тёмного металла и красного свечения. Это отражает характер OBSIDIAN RUSSIA: уверенность, движение и амбиции.</p><p>Информация о завершённых механиках, версии игры и дате открытия появится только после подтверждения командой.</p></div></div><div class="values-grid"><div class="value panel">{icon('users',28)}<h3>СООБЩЕСТВО</h3><p>Игроки — главное в хорошем RolePlay.</p></div><div class="value panel">{icon('shield',28)}<h3>ЧЕСТНЫЙ ПОДХОД</h3><p>Без ложных обещаний о ещё не готовых функциях.</p></div><div class="value panel">{icon('flash',28)}<h3>РАЗВИТИЕ</h3><p>Анонсы, обновления и движение к запуску.</p></div></div></div></section>'''

def rules_page():
    return head('ДОКУМЕНТЫ','ПРАВИЛА <span>САЙТА</span>','Базовые условия использования веб-портала.')+'''<section class="section compact"><div class="shell legal"><h2>1. Общие положения</h2><p>Этот веб-портал предоставляет новости, информацию о проекте и возможности взаимодействия с командой OBSIDIAN RUSSIA. Регистрация в веб-портале сама по себе не означает регистрации игрового персонажа.</p><h2>2. Учётная запись</h2><p>Пользователь обязан защищать свой пароль и не передавать доступ третьим лицам. Запрещены попытки взлома, автоматизированные атаки, спам и злоупотребления сервисом.</p><h2>3. Публикации и обращения</h2><p>Не публикуйте оскорбления, чужие персональные данные, запрещённые материалы, вредоносные ссылки и спам. Администрация вправе закрывать некорректные обращения.</p><h2>4. Доступность</h2><p>Сайт и игровые функции могут изменяться во время разработки. Дата открытия, доступность клиента и серверов объявляются отдельно.</p><h2>5. Контакты</h2><p>Вопросы можно направить через раздел <a href="/contact">поддержки</a> или официальные сообщества, указанные внизу страницы.</p></div></section>'''

def privacy_page(settings):
    support=E(settings.get('support_email',''))
    return head('ДОКУМЕНТЫ','ПОЛИТИКА <span>КОНФИДЕНЦИАЛЬНОСТИ</span>','Информация об обработке данных пользователей веб-портала.')+f'''<section class="section compact"><div class="shell legal"><p><strong>Примечание владельцу:</strong> перед публичным запуском проверь эту политику на соответствие законам страны регистрации оператора и дополни сведениями о юридическом лице, контактах и сроках хранения данных.</p><h2>Какие данные хранятся</h2><p>При регистрации сохраняются логин, адрес электронной почты, статус подтверждения email, хеш пароля и дата создания аккаунта. Для подтверждения адреса и его смены временно сохраняются хеши одноразовых токенов и адреса ожидающие подтверждения. Для входа используются файлы cookie с идентификатором сессии. В обращениях поддержки хранятся тема, текст и статус обращения.</p><h2>Для чего используются данные</h2><p>Для входа в личный кабинет, управления заявками поддержки и защиты учётных записей. Сайт не запрашивает и не хранит банковские реквизиты.</p><h2>Где хранятся данные</h2><p>Информация сохраняется в базе SQLite на сервере владельца сайта. Администратор сервера контролирует хранение и резервные копии.</p><h2>Как связаться</h2><p>Для запроса доступа или удаления аккаунта воспользуйтесь <a href="/contact">поддержкой</a>{(' или напишите на '+support) if support else ''}.</p></div></section>'''

def auth_page(kind,csrf,err='',next_url=''):
    signup=(kind=='register')
    title='СОЗДАТЬ АККАУНТ' if signup else 'ДОБРО ПОЖАЛОВАТЬ'
    fields=(f'''<label>Игровой ник / логин<input name="username" minlength="3" maxlength="24" required pattern="[A-Za-zА-Яа-яЁё0-9_]+" autocomplete="username" placeholder="Например, ObsidianPlayer"></label><label>Email<input type="email" name="email" maxlength="120" required autocomplete="email" placeholder="you@example.com"></label>''' if signup else '''<label>Логин или Email<input name="identity" maxlength="120" required autocomplete="username" placeholder="Логин или Email"></label>''')
    errbox=f'<div class="form-error" role="alert">{E(err)}</div>' if err else ''
    next_hidden=f'<input type="hidden" name="next" value="{E(next_url)}">' if next_url else ''
    next_query=('?next='+quote(next_url,safe='')) if next_url else ''
    return f'''<section class="auth-section"><div class="auth-visual"><img src="/static/avatar.jpg" alt="OBSIDIAN RUSSIA"><div>ТВОЯ ИСТОРИЯ<br><span>НАЧИНАЕТСЯ ЗДЕСЬ.</span></div></div><div class="auth-side"><div class="form-panel"><div class="kicker">ЛИЧНЫЙ КАБИНЕТ</div><h1>{title}</h1><p>{'Создай веб-аккаунт для новостей и обращений.' if signup else 'Войди в свой веб-аккаунт OBSIDIAN RUSSIA.'}</p>{errbox}<form method="post" action="/{'register' if signup else 'login'}" class="form-grid">{csrf_field(csrf)}{next_hidden}{fields}<label>Пароль<input type="password" name="password" minlength="{'10' if signup else '1'}" maxlength="128" required autocomplete="{'new-password' if signup else 'current-password'}" placeholder="••••••••••••"></label>{'<label>Подтверждение пароля<input type="password" name="password2" minlength="10" maxlength="128" required autocomplete="new-password" placeholder="••••••••••••"></label>' if signup else ''}<button class="btn btn-primary" type="submit">{'Создать аккаунт' if signup else 'Войти'} {icon('arrow',18)}</button></form><div class="form-footer">{f'Уже есть аккаунт? <a href="/login{next_query}">Войти</a>' if signup else f'Нет аккаунта? <a href="/register{next_query}">Зарегистрироваться</a>'}</div>{'<p class="small-note"><a href="/forgot">Забыли пароль?</a></p>' if not signup else ''}<p class="small-note">Веб-аккаунт пока не связан с игровым персонажем. Пароль должен быть уникальным.</p></div></div></section>'''

def recovery_request_page(csrf, enabled=False, notice=''):
    info=('<p class="small-note">Если адрес зарегистрирован, мы отправим письмо с одноразовой ссылкой. Проверь также папку «Спам».</p>'
          if enabled else '<p class="small-note">Восстановление по email пока не настроено администратором. Для помощи обратись в поддержку проекта.</p>')
    form=(f'''<form class="form-grid" method="post" action="/forgot">{csrf_field(csrf)}
        <label>Адрес электронной почты<input type="email" name="email" maxlength="120"
        required autocomplete="email" placeholder="you@example.com"></label>
        <button class="btn btn-primary" type="submit">Отправить ссылку</button></form>''' if enabled else '')
    flash=f'<div class="panel dashboard-panel" role="status"><p>{E(notice)}</p></div>' if notice else ''
    return head('ВОССТАНОВЛЕНИЕ','ВОССТАНОВИТЬ <span>ДОСТУП</span>',
                'Смена пароля веб-аккаунта OBSIDIAN RUSSIA.')+f'''<section class="section compact">
        <div class="shell"><div class="panel dashboard-panel">{info}{flash}{form}
        <p class="small-note"><a href="/login">Вернуться ко входу</a></p></div></div></section>'''


def recovery_reset_page(csrf, token, valid):
    if not valid:
        content='<p>Ссылка недействительна или срок её действия истёк. Запроси новую.</p><a class="btn btn-primary" href="/forgot">Новая ссылка</a>'
    else:
        content=f'''<p>Придумай новый пароль. Ссылка действует один раз.</p>
        <form class="form-grid" method="post" action="/reset">{csrf_field(csrf)}
        <input type="hidden" name="token" value="{E(token)}">
        <label>Новый пароль<input type="password" name="password" minlength="10" maxlength="128"
        required autocomplete="new-password"></label>
        <label>Повтори новый пароль<input type="password" name="confirm" minlength="10" maxlength="128"
        required autocomplete="new-password"></label>
        <button class="btn btn-primary" type="submit">Сменить пароль</button></form>'''
    return head('НОВЫЙ ПАРОЛЬ','СОЗДАТЬ <span>НОВЫЙ ПАРОЛЬ</span>')+f'''<section class="section compact">
        <div class="shell"><div class="panel dashboard-panel">{content}</div></div></section>'''


def email_confirmation_page(csrf,token,proof,needs_login=False):
    if not proof:
        body='<p>Ссылка недействительна или просрочена.</p><a class="btn btn-primary" href="/account">Личный кабинет</a>'
    elif needs_login:
        body='<p>Для смены email сначала войди в тот же аккаунт сайта, в котором запрашивал смену.</p><a class="btn btn-primary" href="/login">Войти</a>'
    else:
        action=('Подтвердить новый email' if proof['purpose']=='change'
                else 'Подтвердить email')
        body=f'''<p>Адрес: <strong>{E(proof['pending_email'])}</strong>. Если запрос был отправлен не тобой, не подтверждай его.</p>
        <form method="post" action="/verify-email" class="form-grid">{csrf_field(csrf)}
        <input type="hidden" name="token" value="{E(token)}">
        <button class="btn btn-primary" type="submit">{action}</button></form>'''
    return head('ПОЧТА','ПОДТВЕРЖДЕНИЕ <span>EMAIL</span>')+f'''<section class="section compact">
    <div class="shell"><div class="panel dashboard-panel">{body}</div></div></section>'''


def account_page(c,user,csrf,email_enabled=False):
    tickets=c.execute('SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 10',(user['user_id'],)).fetchall()
    active_sessions=c.execute('SELECT COUNT(*) FROM sessions WHERE user_id=? AND expires_at>?',(user['user_id'],now())).fetchone()[0]
    session_controls=f'''<div class="panel dashboard-panel"><h2>{icon('key',22)} БЕЗОПАСНОСТЬ СЕАНСОВ</h2><p>Активные входы на сайт: <strong>{active_sessions}</strong>. Если заходил с другого устройства, заверши старые сеансы.</p><div class="profile-actions"><form method="post" action="/account/sessions/close-others">{csrf_field(csrf)}<button class="btn btn-outline" type="submit">Завершить другие сеансы</button></form><form method="post" action="/account/sessions/logout-all">{csrf_field(csrf)}<button class="btn btn-outline" type="submit">Выйти на всех устройствах</button></form></div><p class="small-note">Действие относится только к сайту. Сеансы форума и Wiki управляются отдельно.</p></div>'''
    verified=bool(user['email_verified_at'])
    address_notice=('<p class="small-note">Адрес подтверждён. Восстановление пароля по email доступно при настройке SMTP.</p>'
                    if verified else '<p class="small-note">Адрес ещё не подтверждён. Восстановление пароля по email отключено до подтверждения.</p>')
    verify_form=(f'''<form class="form-grid" method="post" action="/account/email/resend">{csrf_field(csrf)}
        <button class="btn btn-outline" type="submit">Отправить письмо для подтверждения</button></form>'''
        if email_enabled and not verified else '')
    change_form=(f'''<form class="form-grid" method="post" action="/account/email/change">{csrf_field(csrf)}
        <label>Новый email<input type="email" name="email" required maxlength="120" autocomplete="email"></label>
        <label>Текущий пароль сайта<input type="password" name="password" required maxlength="128" autocomplete="current-password"></label>
        <button class="btn btn-outline" type="submit">Подтвердить смену по почте</button></form>'''
        if email_enabled else '')
    unavailable=('<p class="small-note">Отправка писем не настроена: подтвердить или изменить адрес пока нельзя.</p>'
                 if not email_enabled else '')
    email_controls=f'''<div class="panel dashboard-panel"><h2>{icon('mail',22)} БЕЗОПАСНОСТЬ EMAIL</h2>
        <p>Текущий адрес: <strong>{E(user['email'])}</strong></p>{address_notice}
        {verify_form}{change_form}{unavailable}
        <p class="small-note">Смена email применяется только после подтверждения нового адреса и требует текущий пароль сайта. При успешной смене старые сеансы закрываются.</p></div>'''
    trows=''.join(f'<div class="ticket-row"><span>#{t["id"]} · {E(t["subject"])}</span>{badge("Открыто" if t["status"]=="open" else "Закрыто","live" if t["status"]=="open" else "muted")}</div>' for t in tickets) or '<p class="muted">Пока нет обращений.</p>'
    return head('ЛИЧНЫЙ КАБИНЕТ',f'ПРИВЕТ, <span>{E(user["username"])}</span>','Управляй веб-аккаунтом и обращениями в поддержку.')+f'''<section class="section compact"><div class="shell dashboard-grid"><div class="panel profile-panel"><div class="profile-avatar">{icon('user',32)}</div><h2>{E(user['username'])}</h2><p>{E(user['email'])}</p>{badge('Администратор' if user['role']=='admin' else 'Участник сообщества','live')}<div class="profile-meta"><span>Дата регистрации</span><strong>{date(user['created_at'])}</strong></div><p class="small-note">Это аккаунт сайта. Данные игрового персонажа будут доступны после подключения игрового сервера.</p><div class="profile-actions">{f'<a class="btn btn-outline" href="/admin">{icon("gear",17)} Админ-панель</a>' if user['role']=='admin' else ''}<form method="post" action="/logout">{csrf_field(csrf)}<button class="btn btn-outline" type="submit">{icon('logout',17)} Выйти</button></form></div></div><div class="dashboard-content"><div class="panel dashboard-panel"><h2>{icon('ticket',22)} МОИ ОБРАЩЕНИЯ</h2>{trows}<a class="text-link" href="/contact">Новое обращение {icon('arrow',17)}</a></div><div class="panel dashboard-panel"><h2>{icon('key',22)} ИЗМЕНИТЬ ПАРОЛЬ</h2><form method="post" action="/account/password" class="form-grid">{csrf_field(csrf)}<label>Текущий пароль<input type="password" name="old_password" required autocomplete="current-password"></label><label>Новый пароль (от 10 символов)<input type="password" name="new_password" required minlength="10" maxlength="128" autocomplete="new-password"></label><button class="btn btn-outline" type="submit">Сохранить новый пароль</button></form></div>{email_controls}{session_controls}</div></div></section>'''

def contact_page(user,csrf,err=''):
    if not user:return head('ПОДДЕРЖКА','ЕСТЬ <span>ВОПРОС?</span>','Для обращения в поддержку войди в личный кабинет.')+f'<section class="section compact"><div class="shell"><div class="panel contact-box"><h2>СВЯЖИСЬ С НАМИ</h2><p>Обращения доступны зарегистрированным пользователям. Так мы сможем сохранить историю запросов.</p><a class="btn btn-primary" href="/login">Войти в аккаунт {icon("arrow",18)}</a></div></div></section>'
    return head('ПОДДЕРЖКА','МЫ НА <span>СВЯЗИ</span>','Отправь обращение команде проекта.')+f'''<section class="section compact"><div class="shell"><div class="panel contact-box"><h2>НОВОЕ ОБРАЩЕНИЕ</h2>{f'<p class="form-error">{E(err)}</p>' if err else ''}<form method="post" action="/contact" class="form-grid">{csrf_field(csrf)}<label>Тема<input name="subject" required maxlength="100" placeholder="Кратко опиши вопрос"></label><label>Сообщение<textarea name="message" required minlength="10" maxlength="3000" rows="7" placeholder="Опиши ситуацию подробно..."></textarea></label><button type="submit" class="btn btn-primary">Отправить обращение {icon('arrow',18)}</button></form></div></div></section>'''

def admin_page(c,tab,csrf,msg=''):
    tabs=[('overview','Обзор'),('news','Новости'),('servers','Серверы'),('tickets','Обращения'),('settings','Настройки')]
    tablinks=''.join(f'<a href="/admin?tab={key}" class="{"selected" if tab==key else ""}">{name}</a>' for key,name in tabs)
    message=f'<div class="form-success">{E(msg)}</div>' if msg else ''
    header=head('УПРАВЛЕНИЕ САЙТОМ','АДМИН-<span>ПАНЕЛЬ</span>','Изменения сохраняются в базе данных сайта.')
    inner=''
    if tab=='overview':
        users=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        posts=c.execute('SELECT COUNT(*) FROM news').fetchone()[0]
        servers=c.execute('SELECT COUNT(*) FROM servers').fetchone()[0]
        tickets=c.execute("SELECT COUNT(*) FROM tickets WHERE status='open'").fetchone()[0]
        inner='<div class="admin-stats">'+''.join(f'<div class="panel stat"><strong>{value}</strong><span>{name}</span></div>' for value,name in [(users,'Пользователей'),(posts,'Публикаций'),(servers,'Серверов'),(tickets,'Открытых обращений')])+'</div><div class="panel admin-info"><h2>ПЕРЕД ПУБЛИЧНЫМ ЗАПУСКОМ</h2><p>Настрой ссылки на скачивание клиента и адреса серверов, проверь тексты юридических документов, включи HTTPS и резервные копии. Не подключай незнакомые платёжные ссылки.</p><p>Статусы серверов сейчас задаются вручную; автоматический онлайн требует отдельной игровой интеграции.</p></div>'
    elif tab=='news':
        posts=c.execute('SELECT * FROM news ORDER BY id DESC').fetchall()
        rows=''.join(f'<div class="admin-row"><div><strong>{E(n["title"])}</strong><small>#{n["id"]} · {date(n["created_at"])} · {"Опубликовано" if n["published"] else "Черновик"}</small></div><div class="row-actions"><a href="/admin?tab=news&edit={n["id"]}" class="tiny-btn">Изменить</a><form method="post" action="/admin/news/delete" data-confirm="Удалить новость без возможности восстановления?">{csrf_field(csrf)}<input type="hidden" name="id" value="{n["id"]}"><button type="submit" class="tiny-btn danger">Удалить</button></form></div></div>' for n in posts)
        inner=f'<div class="panel admin-info"><h2>ВСЕ ПУБЛИКАЦИИ</h2>{rows or "Публикаций нет"}</div>'
        inner+= '<div class="panel admin-info"><h2>РЕДАКТОР НОВОСТИ</h2>'
        inner+='<div id="admin-news-form">'+admin_news_form(c,csrf)+'</div></div>'
    elif tab=='servers':
        servers=c.execute('SELECT * FROM servers ORDER BY id').fetchall()
        inner='<div class="panel admin-info"><h2>НАСТРОЙКИ СЕРВЕРОВ</h2><p>Вручную укажи статус и онлайн. Никакие данные автоматически не запрашиваются из игры.</p>'
        for s in servers:
            opt=''.join(f'<option value="{x}" {"selected" if s["status"]==x else ""}>{y}</option>' for x,y in [('soon','Скоро'),('online','Работает'),('offline','Недоступен')])
            inner+=f'''<form class="admin-server-form" method="post" action="/admin/servers/save">{csrf_field(csrf)}<input type="hidden" name="id" value="{s['id']}"><div class="form-row"><label>Название<input name="name" maxlength="70" value="{E(s['name'])}" required></label><label>Адрес сервера<input name="address" maxlength="140" value="{E(s['address'])}" placeholder="Пока неизвестен"></label></div><label>Описание<input name="description" maxlength="200" value="{E(s['description'])}"></label><div class="form-row"><label>Статус<select name="status">{opt}</select></label><label>Онлайн<input name="online" type="number" min="0" max="100000" value="{s['online']}"></label><label>Вместимость<input name="capacity" type="number" min="0" max="100000" value="{s['capacity']}"></label></div><button class="btn btn-outline" type="submit">Сохранить сервер #{s['id']}</button></form>'''
        inner+='</div><div class="panel admin-info"><h2>НОВЫЙ СЕРВЕР</h2><form method="post" action="/admin/servers/add" class="form-grid">'+csrf_field(csrf)+'<label>Название<input name="name" maxlength="70" required placeholder="OBSIDIAN #02"></label><label>Описание<input name="description" maxlength="200" placeholder="Описание сервера"></label><button class="btn btn-primary" type="submit">Добавить сервер</button></form></div>'
    elif tab=='tickets':
        tickets=c.execute('SELECT t.*,u.username FROM tickets t JOIN users u ON u.id=t.user_id ORDER BY t.id DESC LIMIT 100').fetchall()
        inner='<div class="panel admin-info"><h2>ОБРАЩЕНИЯ ПОЛЬЗОВАТЕЛЕЙ</h2>'
        for t in tickets:
            inner+=f'''<div class="admin-ticket"><div class="ticket-heading"><strong>#{t['id']} · {E(t['subject'])}</strong>{badge('Открыто' if t['status']=='open' else 'Закрыто','live' if t['status']=='open' else 'muted')}</div><small>{E(t['username'])} · {date(t['created_at'])}</small><p>{E(t['message'])}</p><form action="/admin/tickets/status" method="post">{csrf_field(csrf)}<input type="hidden" name="id" value="{t['id']}"><input type="hidden" name="status" value="{'closed' if t['status']=='open' else 'open'}"><button class="tiny-btn" type="submit">{'Закрыть' if t['status']=='open' else 'Открыть снова'}</button></form></div>'''
        inner+= '</div>'
    elif tab=='settings':
        settings={r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}
        labels=[('vk','Сообщество VK (https://...)'),('telegram','Канал Telegram (https://...)'),('forum','Ссылка на форум'),('android_download','Ссылка на Android-клиент'),('windows_download','Ссылка на Windows-клиент'),('donation_url','Официальная ссылка магазина / платёжного провайдера'),('support_email','Почта поддержки')]
        fields=''.join(f'<label>{name}<input name="{key}" maxlength="500" value="{E(settings.get(key,""))}" placeholder="https://..."></label>' for key,name in labels)
        inner=f'''<div class="panel admin-info"><h2>НАСТРОЙКИ ПРОЕКТА</h2><p>Любые неуказанные ссылки останутся неактивными. Не используй ссылку на магазин, пока не настроен учёт оплат и выдача покупок.</p><form method="post" action="/admin/settings" class="form-grid">{csrf_field(csrf)}{fields}<label>Информационный баннер<textarea name="site_notice" maxlength="400" rows="3">{E(settings.get('site_notice',''))}</textarea></label><button class="btn btn-primary" type="submit">Сохранить настройки</button></form></div>'''
    return header+f'<section class="section compact"><div class="shell"><div class="admin-tabs">{tablinks}</div>{message}<div class="admin-content">{inner}</div></div></section>'

def admin_news_form(c,csrf):
    n=None
    # The editor is requested by query string in app.py. See admin_news_form_for_item.
    return admin_news_form_for_item(None,csrf)

def admin_news_form_for_item(n,csrf):
    g=lambda k,default='':E(n[k] if n else default)
    return f'''<form method="post" action="/admin/news/save" class="form-grid">{csrf_field(csrf)}<input type="hidden" name="id" value="{g('id')}"><label>Заголовок<input name="title" maxlength="130" required value="{g('title')}"></label><label>Короткий текст<input name="excerpt" maxlength="250" required value="{g('excerpt')}"></label><label>Категория<select name="category">{''.join(f'<option value="{cat}" {"selected" if (n and n["category"]==cat) else ""}>{cat}</option>' for cat in ['Новости','Разработка','Обновление','События','Важно'])}</select></label><label>Текст новости<textarea name="body" required rows="10" maxlength="20000">{g('body')}</textarea></label><label class="checkbox-line"><input type="checkbox" name="published" value="1" {'checked' if (n is None or n['published']) else ''}> Опубликовать новость</label><button class="btn btn-primary" type="submit">{'Сохранить изменения' if n else 'Создать новость'}</button>{'<a class="text-link" href="/admin?tab=news">Отменить редактирование</a>' if n else ''}</form>'''

def not_found():
    return '<section class="section"><div class="shell not-found"><span>404</span><h1>СТРАНИЦА НЕ НАЙДЕНА</h1><p>Возможно, ссылка устарела или страница была перемещена.</p><a class="btn btn-primary" href="/">На главную '+icon('arrow',18)+'</a></div></section>'
