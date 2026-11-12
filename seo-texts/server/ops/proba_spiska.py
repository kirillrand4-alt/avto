# -*- coding: utf-8 -*-
"""Точная проба списка адресов (proba_tochnaya) с параллелью по доменам и щадящим темпом: крупные публичные домены —
не чаще раза в 20 с, прочие — раз в 3 с на домен, всего до 8 потоков. Свежий окончательный вердикт (есть / нет ящика /
нет MX / принимает всё, моложе 30 дней) переиспользуем. Временные ответы — второй круг через 15 мин.
Вход: jsonl на сервере с полем emails (по умолчанию _ops/meyer-provaly2.jsonl, только записи без stop).
Журнал _ops/proba-<имя>.jsonl (резюмируемо), итог в лог.
    proba_spiska.py --zapusk [--vhod=meyer-provaly2.jsonl] [--imya=meyer-provaly]"""
import io, json, os, re, sqlite3, subprocess, sys, threading, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
ОПС = r"C:\sender\_ops"
арг = lambda к, д: next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--%s=" % к)), д)
ИМЯ = арг("imya", "meyer-provaly"); ВХОД = os.path.join(ОПС, арг("vhod", "meyer-provaly2.jsonl"))
if "--zapusk" in sys.argv:
    л = io.open(os.path.join(ОПС, "proba-%s.log" % ИМЯ), "a", encoding="utf-8")
    п = subprocess.Popen([sys.executable, "-u", os.path.abspath(__file__)] + [x for x in sys.argv[1:] if x != "--zapusk"],
                         cwd=r"C:\sender", stdout=л, stderr=л, creationflags=0x00000008 | 0x00000200)
    time.sleep(5); print("запущен, pid %d" % п.pid); sys.exit(0)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proba_tochnaya as P   # noqa: E402
ЖУР = os.path.join(ОПС, "proba-%s.jsonl" % ИМЯ)
КРУПНЫЕ = {"mail.ru", "bk.ru", "list.ru", "inbox.ru", "internet.ru", "yandex.ru", "ya.ru", "yandex.com", "gmail.com", "rambler.ru", "ro.ru", "lenta.ru", "autorambler.ru", "myrambler.ru"}
адреса = []
for с in io.open(ВХОД, encoding="utf-8"):
    x = json.loads(с)
    if x.get("stop"): continue
    for e in x.get("emails") or []:
        e = e.strip().lower()
        if re.fullmatch(r"[^@\s;,]+@[^@\s;,]+\.[a-z0-9\-]+", e) and e not in адреса: адреса.append(e)
сделано = {}
if os.path.exists(ЖУР):
    for с in io.open(ЖУР, encoding="utf-8"):
        try: з = json.loads(с); сделано[з["email"]] = з
        except (ValueError, KeyError): pass
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True)
кэш = {em: (v, str(ts)) for em, v, ts in c.execute("SELECT lower(email), verdict, ts FROM addr_probe")}
порог = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 30 * 86400))
_зам = threading.Lock(); _посл = defaultdict(float); _домзам = defaultdict(threading.Lock); сч = Counter()


def пиши(з):
    with _зам:
        with io.open(ЖУР, "a", encoding="utf-8") as ф:
            ф.write(json.dumps(з, ensure_ascii=False) + "\n"); ф.flush(); os.fsync(ф.fileno())
        сделано[з["email"]] = з; сч["круг %d: %s" % (з["krug"], з["itog"])] += 1
        if sum(сч.values()) % 50 == 0: print(time.strftime("%H:%M:%S"), sum(сч.values()), dict(сч), flush=True)


def одна(args):
    адрес, круг = args
    домен = адрес.rsplit("@", 1)[1]
    with _домзам[домен]:                       # один разговор с доменом за раз + пауза
        пауза = 20 if домен in КРУПНЫЕ else 3
        ждать = _посл[домен] + пауза - time.time()
        if ждать > 0: time.sleep(ждать)
        try: в, код, ответ, мх = P.проба(адрес)
        except Exception as ex: в, код, ответ, мх = "неясно", None, "сбой: %s" % str(ex)[:120], ""  # noqa: BLE001,E701
        _посл[домен] = time.time()
    P.в_базы(адрес, в, код, ответ, мх)
    пиши({"email": адрес, "krug": круг, "itog": в, "kod": код, "otvet": ответ, "mx": мх, "vremenny": P.временный(в, код, ответ)})


очередь = []
for e in адреса:
    if e in сделано: continue
    v, ts = кэш.get(e, ("", ""))
    if v in ("есть", "нет ящика", "нет MX", "принимает всё") and ts[:10] >= порог:
        пиши({"email": e, "krug": 0, "itog": v, "otvet": "кэш addr_probe от %s" % ts[:10], "vremenny": False}); continue
    очередь.append(e)
print("адресов %d, уже в журнале %d, к пробе %d" % (len(адреса), len(сделано), len(очередь)), flush=True)
# крупные домены — вперемешку с прочими, чтобы потоки не стояли в очереди к одному домену
очередь.sort(key=lambda e: (e.rsplit("@", 1)[1] in КРУПНЫЕ, e.rsplit("@", 1)[1]))
with ThreadPoolExecutor(max_workers=8) as пул: list(пул.map(одна, [(e, 1) for e in очередь]))
вр = [e for e, з in сделано.items() if з.get("vremenny") and з.get("krug") == 1]
if вр:
    print("второй круг: %d временных, ждём 15 мин" % len(вр), flush=True); time.sleep(900)
    with ThreadPoolExecutor(max_workers=8) as пул: list(пул.map(одна, [(e, 2) for e in вр]))
итог = Counter(з["itog"] for з in сделано.values())
print("ИТОГ ПРОБЫ %s: адресов %d %s" % (ИМЯ, len(сделано), dict(итог)), flush=True)
