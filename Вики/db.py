"""OBSIDIAN RUSSIA WIKI persistence, stdlib SQLite only."""
import os, sqlite3, hashlib, hmac, secrets, re, unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = Path(os.getenv('OBWIKI_DATA_DIR', str(ROOT / 'data'))).resolve()
DB = DATA / 'wiki.sqlite3'

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def connect():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    first = not DB.exists()
    if first: DB.touch(mode=0o600)
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=15000')
    c.execute('PRAGMA journal_mode=WAL')
    return c

CATEGORIES = [
 ('start','Начало игры','Основы, первые шаги и полезные советы','🚀'),
 ('transport','Транспорт','Автомобили, гаражи и обслуживание','🚘'),
 ('jobs','Работы','Профессии и способы развития персонажа','💼'),
 ('factions','Организации','Государственные и неофициальные объединения','🏛️'),
 ('property','Недвижимость','Дома, квартиры, гаражи и владение','🏘️'),
 ('business','Бизнесы','Управление бизнесом и экономика проекта','🏪'),
 ('items','Предметы','Инвентарь, экипировка и взаимодействия','🎒'),
 ('systems','Игровые системы','Интерфейс, прогресс и игровые механики','⚙️'),
 ('community','Правила и помощь','Безопасность, поддержка и сообщество','🛡️'),
]

CATALOG_TYPES = [
 ('transport','Транспорт','Автомобили и другой игровой транспорт','🚘'),
 ('skins','Скины','Внешний вид и образы персонажей','🧍'),
 ('property','Недвижимость','Дома, квартиры и гаражи','🏠'),
 ('business','Бизнесы','Предприятия и экономика','🏪'),
 ('jobs','Работы','Доступные профессии','💼'),
 ('items','Предметы','Инвентарь и игровые вещи','🎒'),
]

ARTICLES = [
('pervye-shagi','start','Первые шаги в OBSIDIAN RUSSIA','Как подготовиться к первой игровой сессии, освоить управление и выбрать направление развития.', 'Новичкам',1, '''# Добро пожаловать в OBSIDIAN RUSSIA

OBSIDIAN RUSSIA — игровой RolePlay-проект. Эта база знаний помогает знакомиться с возможностями проекта и находить ответы на частые вопросы.

## Что сделать перед началом

- Следите за объявлениями в официальных сообществах.
- Установите игровой клиент по ссылке, опубликованной командой проекта.
- Ознакомьтесь с правилами сервера и ролевого взаимодействия.
- Не передавайте пароль и коды подтверждения другим людям.

## Первые действия в игре

- Изучите интерфейс и назначение основных кнопок.
- Посмотрите доступные задания, работы и организации.
- Учитывайте баланс персонажа и расходы на транспорт.
- При затруднениях обратитесь в раздел помощи.

> Данный материал — базовый ориентир. Конкретные команды и механики будут уточняться после запуска серверов.

## Полезные ссылки

- [Сообщество VK](https://vk.ru/obsidian_brussia)
- [Telegram](https://t.me/obsidian_brussia)'''),
('kak-nachat-igrat','start','Как начать играть','Порядок подготовки клиента и проверка официальных источников.', 'Новичкам',0,'''# Установка и запуск

## 1. Проверьте источники

Загружайте клиент только из официальных объявлений OBSIDIAN RUSSIA. Не устанавливайте сборки из неизвестных архивов и сообщений.

## 2. Подготовьте устройство

Проверьте свободную память, подключение к интернету и доступ к необходимым разрешениям приложения.

## 3. Создайте игровой аккаунт

Следуйте подсказкам клиента. Используйте уникальный пароль и не публикуйте данные для входа.

## 4. Начните знакомство

Прочитайте игровые правила и найдите сведения о доступных системах в этой Wiki.

> Ссылка на клиент будет опубликована администрацией, когда сборка будет готова.'''),
('osnovy-rp','start','Основы RolePlay','Принципы отыгровки, уважения к другим игрокам и ролевого взаимодействия.', 'Новичкам',0,'''# Что такое RolePlay

RolePlay (RP) — отыгрывание действий и решений от лица игрового персонажа.

## Общие принципы

- Отделяйте игровую ситуацию от реального общения.
- Уважайте других участников и их время.
- Развивайте историю персонажа последовательно.
- Не используйте ошибки игры ради преимущества.

## Важно

Этот текст является объяснением жанра. Официальные правила публикуются отдельно и имеют приоритет.'''),
('spisok-serverov','start','Серверы и подключение','Где искать актуальные адреса, информацию о доступности и новости запуска.', 'Новичкам',0,'''# Серверы OBSIDIAN RUSSIA

Актуальный список игровых серверов будет опубликован в официальных сообществах проекта и на основном сайте после запуска.

## Как выбрать сервер

- Ознакомьтесь с названием и доступностью сервера.
- Уточните, разрешён ли перенос персонажа между серверами.
- Следите за объявлениями об обслуживании.

> Сейчас Wiki не подключена к игровому API. Онлайн и IP-адреса здесь намеренно не выдумываются.'''),
('klass-avtomobiley','transport','Классы транспорта','Как различать легковой, коммерческий и специальный транспорт.', 'Справочник',1,'''# Классы транспорта

Раздел поможет ориентироваться в типах транспорта, которые могут встречаться на RolePlay-серверах.

## Легковые автомобили

Подходят для повседневных перемещений и личного использования.

## Внедорожники

Обычно выделяются высоким клиренсом и универсальностью.

## Грузовой транспорт

Используется для перевозок и рабочих сценариев.

## Специальная техника

Может быть связана с отдельными профессиями и организациями.

> Каталог моделей, точные характеристики и цены OBSIDIAN RUSSIA будут добавлены после утверждения игрового автопарка.'''),
('pokupka-avto','transport','Покупка и продажа автомобиля','Рекомендации по безопасной торговле транспортом в игровом мире.', 'Справочник',0,'''# Сделки с автомобилями

Перед покупкой уточняйте характеристики автомобиля и доступные на сервере способы передачи собственности.

## Рекомендации

- Проверяйте цену и модель до подтверждения сделки.
- Используйте только предусмотренный игрой механизм торговли.
- Не соглашайтесь на сделки за реальные деньги вне официального магазина.
- Сохраняйте необходимые доказательства нарушения правил.

> Точный порядок сделок зависит от реализации игрового сервера.'''),
('garazh-i-hranenie','transport','Гаражи и хранение','Основные вопросы о парковке, гаражных местах и хранении машин.', 'Справочник',0,'''# Хранение транспорта

## Что нужно учитывать

- Количество доступных парковочных мест.
- Условия хранения и доступа к автомобилю.
- Ограничения на использование служебной техники.

> Механики гаражей и лимиты транспорта пока уточняются. Администратор Wiki сможет заменить эту статью актуальными параметрами.'''),
('professii','jobs','Список профессий','Обзор направлений работы и полезных критериев выбора профессии.', 'Справочник',1,'''# Выбор работы

Работы позволяют развивать персонажа и участвовать в игровой экономике.

## Виды деятельности

- Доставка и логистика.
- Перевозка пассажиров.
- Службы города.
- Работа в организациях.
- Предпринимательство.

## Как выбрать направление

Ориентируйтесь на доступное время, предпочитаемый стиль игры и требования к допуску.

> Это ориентировочные виды деятельности. Список фактически реализованных работ будет опубликован после утверждения игрового режима.'''),
('nachalo-karery','jobs','Как построить карьеру','Планирование развития персонажа: первые заработки, расходы и навыки.', 'Новичкам',0,'''# Карьерный путь

## Начальный этап

Сначала изучите доступные роли и правила трудоустройства.

## Развитие

Ставьте реалистичные цели, следите за доходами и планируйте расходы.

## Работа в команде

Фракции и объединения могут открывать новые возможности для ролевой игры.

> Конкретные зарплаты и требования к уровням ещё не подтверждены.'''),
('gosorganizatsii','factions','Государственные организации','Общие принципы работы государственных игровых фракций.', 'Справочник',1,'''# Государственные фракции

Государственные организации на RP-проектах дают возможность участвовать в служебных ролевых сценариях.

## Особенности

- Устав и иерархия должностей.
- Соблюдение внутренней дисциплины.
- Ролевые обязанности сотрудников.
- Взаимодействие с гражданами и другими структурами.

> Список официальных организаций OBSIDIAN RUSSIA и их требования будут опубликованы администрацией.'''),
('semji-i-obedineniya','factions','Семьи и объединения','Организация сообщества игроков, правила взаимодействия и совместные занятия.', 'Справочник',0,'''# Объединения игроков

Семьи и клубы помогают создавать долгосрочные RP-истории.

## Организация

- Определите концепцию и направления деятельности.
- Согласуйте правила общения и участия.
- Разделите обязанности между участниками.
- Соблюдайте общие правила сервера.

> Условия регистрации семей и клубов уточняются.'''),
('nedvizhimost','property','Виды недвижимости','Квартиры, дома и другие объекты в игровой экономике.', 'Справочник',1,'''# Недвижимость

Дома и квартиры могут быть частью экономики персонажа, а также местом для ролевых встреч.

## На что обратить внимание

- Местоположение объекта.
- Доступность помещений.
- Возможности хранения.
- Правила владения и передачи.

> Каталог недвижимости и актуальные цены появятся после наполнения игровой базы.'''),
('pokupka-doma','property','Покупка дома','Что проверить перед приобретением игровой недвижимости.', 'Справочник',0,'''# Приобретение недвижимости

Проверяйте информацию о выбранном объекте и используйте только игровые механизмы передачи собственности.

## Перед сделкой

- Уточните стоимость и дополнительные условия.
- Проверьте, кому принадлежит объект.
- Прочитайте правила использования недвижимости.

> Подтверждённых цен и точной процедуры для OBSIDIAN RUSSIA пока нет.'''),
('biznes','business','Как устроен игровой бизнес','Доход, расходы, управление и основные принципы внутриигрового предпринимательства.', 'Справочник',1,'''# Бизнес на RolePlay-проекте

Бизнесы могут формировать важную часть виртуальной экономики.

## Управление

- Анализируйте спрос на товары и услуги.
- Сопоставляйте потенциальный доход с расходами.
- Следите за ресурсами и состоянием предприятия.
- Соблюдайте правила торговли.

> Типы предприятий, налоги, прибыль и другие значения будут описаны после запуска игровых механик.'''),
('ekonomika','business','Экономика и безопасность сделок','Основные принципы ответственного использования внутриигровой валюты.', 'Справочник',0,'''# Экономика игры

## Планирование

Разделяйте ежедневные расходы, накопления и средства для крупных покупок.

## Защита от мошенничества

- Не сообщайте реквизиты аккаунта другим игрокам.
- Не передавайте доступ к аккаунту в обмен на обещанные бонусы.
- Используйте официальные игровые способы обмена.

> Реальная экономика проекта и ценовые диапазоны будут уточняться.'''),
('inventar','items','Инвентарь и предметы','Общие сведения о хранении, использовании и организации вещей.', 'Справочник',1,'''# Инвентарь

В играх жанра RolePlay инвентарь помогает управлять предметами персонажа.

## Советы

- Следите за назначением и ценностью предметов.
- Учитывайте игровые ограничения на хранение.
- Проверяйте получателя перед передачей вещей.

> Интерфейс инвентаря и перечень предметов будут описаны после окончательной реализации.'''),
('upravlenie','systems','Управление и интерфейс','Раздел о назначении основных элементов управления и меню.', 'Новичкам',1,'''# Управление

Изучите подсказки игрового клиента и доступные настройки управления.

## Основные элементы

- Навигация и перемещение.
- Взаимодействие с объектами.
- Инвентарь и профиль.
- Общение с другими игроками.

> Точные сочетания клавиш и расположение элементов интерфейса зависят от версии клиента.'''),
('progress','systems','Развитие персонажа','Общие принципы игрового прогресса, целей и планирования.', 'Справочник',0,'''# Прогресс персонажа

Выбирайте направление развития: профессия, организация, транспорт или собственное дело.

## Полезный подход

- Ставьте небольшие цели.
- Участвуйте в ролевых событиях.
- Изучайте обновления игровых систем.
- Не используйте сторонние программы для нечестного преимущества.

> Система уровней и наград OBSIDIAN RUSSIA будет описана после подтверждения механик.'''),
('bezopasnost','community','Безопасность аккаунта','Как защитить учётную запись и распознавать мошеннические сообщения.', 'Важно',1,'''# Защита аккаунта

- Используйте длинный уникальный пароль.
- Не передавайте никому пароль, коды из сообщений или токены.
- Проверяйте адрес сайта перед входом.
- Не скачивайте неофициальные программы и плагины.
- Обращайтесь к команде проекта при подозрении на взлом.

## Официальные сообщества

- [VK](https://vk.ru/obsidian_brussia)
- [Telegram](https://t.me/obsidian_brussia)

> Администрация не должна запрашивать пароль от вашего аккаунта в личных сообщениях.'''),
('svyaz-s-komandoj','community','Как связаться с командой','Куда отправлять вопросы, предложения и сообщения об ошибках.', 'Новичкам',0,'''# Обратная связь

Для вопросов и предложений используйте официальные сообщества:

- [OBSIDIAN RUSSIA в VK](https://vk.ru/obsidian_brussia)
- [OBSIDIAN RUSSIA в Telegram](https://t.me/obsidian_brussia)

## Если заметили ошибку

Опишите ожидаемый результат, фактическое поведение и последовательность действий, при которой проявляется проблема. Не публикуйте приватные данные и пароли.'''),
('pravila-viki','community','Правила базы знаний','Как подготавливать полезные материалы и указывать достоверные сведения.', 'Важно',0,'''# Редакционные принципы

Материалы Wiki должны быть понятными, проверяемыми и соответствующими реальному состоянию проекта.

## Требования

- Не публикуйте неподтверждённые цены, IP-адреса и настройки как достоверные.
- Указывайте даты и версии, если информация быстро меняется.
- Не копируйте сторонние статьи без разрешения.
- Не добавляйте личные данные пользователей.

> Все стартовые статьи — редакционные заготовки и должны быть сверены командой проекта до публичного запуска.'''),
]

def init_db():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
          pass_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'editor' CHECK(role IN ('admin','editor')),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          csrf TEXT NOT NULL, expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS categories (
          id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
          description TEXT NOT NULL DEFAULT '', icon TEXT NOT NULL DEFAULT '📖', sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS articles (
          id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE,
          category_id INTEGER NOT NULL REFERENCES categories(id),
          title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', content TEXT NOT NULL,
          difficulty TEXT NOT NULL DEFAULT 'Справочник', image_path TEXT NOT NULL DEFAULT '',
          featured INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'published' CHECK(status IN ('published','draft')),
          sample INTEGER NOT NULL DEFAULT 0, views INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS revisions (
          id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
          user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
          snapshot TEXT NOT NULL, saved_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS catalog_items (
          id INTEGER PRIMARY KEY, kind TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
          title TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
          tier TEXT NOT NULL DEFAULT '', price_text TEXT NOT NULL DEFAULT '',
          parameters TEXT NOT NULL DEFAULT '', image_path TEXT NOT NULL DEFAULT '',
          sample INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('published','draft')),
          created_at TEXT NOT NULL,updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_kind ON catalog_items(kind,status,title);
        CREATE TABLE IF NOT EXISTS media (
          id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
          uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit (
          id INTEGER PRIMARY KEY, actor INTEGER REFERENCES users(id) ON DELETE SET NULL,
          action TEXT NOT NULL, target TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category_id,status,updated_at);
        CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status,featured,updated_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
        ''')
        if c.execute('SELECT COUNT(*) FROM categories').fetchone()[0]==0:
            for i,(slug,title,description,icon) in enumerate(CATEGORIES):
                c.execute('INSERT INTO categories(slug,title,description,icon,sort_order) VALUES(?,?,?,?,?)',(slug,title,description,icon,i))
        if c.execute('SELECT COUNT(*) FROM articles').fetchone()[0]==0:
            ids={r['slug']:r['id'] for r in c.execute('SELECT id,slug FROM categories')}
            for slug,category,title,summary,difficulty,featured,body in ARTICLES:
                c.execute('''INSERT INTO articles(slug,category_id,title,summary,content,difficulty,featured,status,sample,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,'published',1,?,?)''',(slug,ids[category],title,summary,body,difficulty,featured,now(),now()))

def hash_password(password):
    salt=secrets.token_bytes(16)
    iterations=360000
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,iterations)
    return f'pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}'

def verify_password(password, encoded):
    try:
        algorithm, iterations, salt, digest=encoded.split('$')
        i=int(iterations)
        if algorithm!='pbkdf2_sha256' or not 200000<=i<=1000000:return False
        test=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),i)
        return hmac.compare_digest(test,bytes.fromhex(digest))
    except (ValueError,TypeError):return False

def create_session(c,user_id):
    token=secrets.token_urlsafe(40)
    c.execute('INSERT INTO sessions VALUES (?,?,?,?)',(
        hashlib.sha256(token.encode()).hexdigest(),user_id,secrets.token_urlsafe(32),
        (datetime.now(timezone.utc)+timedelta(days=7)).isoformat(timespec='seconds')))
    return token

def session_for(c,token):
    if not token or len(token)>256:return None
    return c.execute('''SELECT u.id,u.username,u.role,s.csrf,s.token_hash FROM sessions s
        JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?''',
        (hashlib.sha256(token.encode()).hexdigest(),now())).fetchone()

def audit(c,user_id,action,target):
    c.execute('INSERT INTO audit(actor,action,target,created_at) VALUES(?,?,?,?)',(user_id,action,str(target)[:200],now()))
