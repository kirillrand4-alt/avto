# -*- coding: utf-8 -*-
"""Проверка адресов партии САМИМ основным сервером, без работника на VPS.

Владелец 17.08: «функции работника вроде есть и на основном сервере - можем
через него проверить». Проверено голым сокетом: исходящий 25-й порт с сервера
ОТКРЫТ (yandex, mail.ru, gmail отвечают баннером), настоящие пробы дают живые
коды. Значит проверять можно здесь и не зависеть от VPS.

Вежливость к чужим серверам не выброшена, а перенесена: адреса разложены по
доменам, каждый домен достаётся РОВНО ОДНОМУ потоку, а внутри потока стоит
штатная пауза AddrProbe. То есть один чужой сервер по-прежнему получает не
чаще одной пробы в N секунд, а разные домены идут параллельно.

Durable: вердикт ложится в addr_probe (база панели) в тот же миг, плюс
дублируется в enrich.db и в obzvon-index.db - три места, как заведено.
Резюмируемо: повторный запуск пропускает всё, что уже с вердиктом.

ПРИМЕНЕНИЕ ВЕРДИКТА ТОЙ ЖЕ ПАРТИЕЙ. Проверка без применения бесполезна:
12.08 прогон нашёл 76 мёртвых и закончился строкой «снято писем: 0». Здесь
приговор («нет ящика», «нет MX») сразу снимает письмо из очереди и уводит
адрес в стоп-лист.

argv: [потоков=6] [лимит_секунд=1600] [пауза_на_домен=3.0]
"""
import io
import json
import os
import sqlite3
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, r"C:\sender")
from sender.addr_probe import AddrProbe                        # noqa: E402
from sender.config import Config                               # noqa: E402
from sender.dtos import SuppressionIn                          # noqa: E402
from sender.store import Store                                 # noqa: E402

ГРУППА = "Партия 935"
ЖУРНАЛ = r"C:\sender\_ops\proba-partii-server.jsonl"
ОБЗВОН = r"C:\sender\obzvon-index.db"
ПРИГОВОР = ("нет ящика", "нет MX")

ПОТОКОВ = int(sys.argv[1]) if len(sys.argv) > 1 else 6
ЛИМИТ_СЕК = (int(sys.argv[2]) if len(sys.argv) > 2 else 1600) - 120
ПАУЗА = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
СТАРТ = time.time()

cfg = Config.load(r"C:\sender\sender.yaml")
БАЗА = cfg.get("service.db_path", r"C:\sender\sender.db")
store = Store(БАЗА)


def _нас(ключ, умолч=None):
    try:
        return cfg.get(f"addr_probe.{ключ}", умолч)
    except Exception:                                          # noqa: BLE001
        return умолч


# Каждому потоку - свой экземпляр пробы: у него свой счётчик паузы, а домены
# между потоками не пересекаются, поэтому чужой сервер частоты не почувствует.
def _проба():
    return AddrProbe(
        БАЗА, helo=str(_нас("helo", "") or ""),
        mail_from=str(_нас("mail_from", "") or ""),
        ttl_days=int(_нас("ttl_days", 30) or 30), pause_sec=ПАУЗА,
        per_domain=100000,           # свой предел держим раскладкой по доменам
        timeout=float(_нас("timeout_sec", 15) or 15),
        source_ip=str(_нас("source_ip", "") or ""))


# --- кого проверяем ------------------------------------------------------
группы = store.recipient_groups().get("по_id") or {}
кэш = _проба()
адрес_кому = {}
for rid, g in группы.items():
    if ГРУППА not in g:
        continue
    rec = store.get_recipient(rid)
    e = str(getattr(rec, "email", "") or "").strip().lower()
    if e and "@" in e:
        адрес_кому.setdefault(e, rid)
всего_в_группе = len(адрес_кому)
ждут = [e for e in адрес_кому if not кэш.cached(e)]

print(f"адресов в группе {всего_в_группе} | с вердиктом "
      f"{всего_в_группе - len(ждут)} | ЖДУТ ПРОВЕРКИ {len(ждут)}")
if not ждут:
    print("проверять нечего")
    raise SystemExit(0)

по_домену = defaultdict(list)
for e in ждут:
    по_домену[e.rsplit("@", 1)[-1]].append(e)
домены = sorted(по_домену, key=lambda d: -len(по_домену[d]))
print(f"доменов {len(домены)}, самый крупный: {домены[0]} "
      f"({len(по_домену[домены[0]])} адресов)")

# Домены раскладываем «змейкой» по потокам, чтобы крупные не собрались в одном.
корзины = [[] for _ in range(ПОТОКОВ)]
for i, d in enumerate(домены):
    корзины[i % ПОТОКОВ].append(d)

замок = threading.Lock()
счёт = Counter()
для_обогащения = []
готово = [0]


def _записать(строка):
    with замок:
        with io.open(ЖУРНАЛ, "a", encoding="utf-8") as f:
            f.write(json.dumps(строка, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())


def _применить(res):
    """Приговор - сразу в дело: письмо снять, адрес в стоп-лист."""
    снято = 0
    try:
        письма = [r for r in (store.confirm_list(status="pending",
                                                 limit=100000) or [])
                  if str(r.get("email") or "").strip().lower() == res["email"]]
        причина = (f"у домена нет почтового сервера: {res.get('answer','')[:60]}"
                   if res["verdict"] == "нет MX" else
                   f"адрес не существует: {res.get('code')} "
                   f"{str(res.get('answer'))[:60]}")
        for р in письма:
            if store.confirm_decide(int(р["id"]), status="skipped",
                                    decided_by="проба с сервера",
                                    reason=причина):
                снято += 1
        store.suppression_add(SuppressionIn(
            scope="email", value=res["email"], reason="bounce_hard",
            source="addr_probe_server"))
    except Exception as ex:                                    # noqa: BLE001
        print(f"    применить не вышло для {res['email']}: {str(ex)[:80]}")
    return снято


def _поток(номер):
    p = _проба()
    p.new_pass()
    свои = [e for d in корзины[номер] for e in по_домену[d]]
    for e in свои:
        if time.time() - СТАРТ > ЛИМИТ_СЕК:
            return
        try:
            res = p.probe(e)
        except Exception as ex:                                # noqa: BLE001
            res = {"email": e, "verdict": "неясно", "answer": str(ex)[:90]}
        в = str(res.get("verdict") or "неясно")
        снято = _применить(res) if в in ПРИГОВОР else 0
        with замок:
            счёт[в] += 1
            счёт["снято_писем"] += снято
            готово[0] += 1
            для_обогащения.append({"email": e, "verdict": в,
                                   "answer": res.get("answer")})
            n = готово[0]
        _записать({"email": e, "verdict": в, "code": res.get("code"),
                   "answer": str(res.get("answer") or "")[:200],
                   "снято_писем": снято,
                   "ts": datetime.now(timezone.utc).isoformat()})
        if n % 25 == 0:
            print(f"  [{n}/{len(ждут)}] {dict(счёт)} "
                  f"{int(time.time()-СТАРТ)}с")


with ThreadPoolExecutor(max_workers=ПОТОКОВ) as pool:
    list(pool.map(_поток, range(ПОТОКОВ)))

print(f"\nпроверено за проход: {готово[0]} из {len(ждут)}")
for k, n in счёт.most_common():
    print(f"  {k:<16} {n}")

# --- вердикты в две другие базы -----------------------------------------
try:
    from sender.probe_enrich import найти as _найти, записать as _в_обогащение
    n = _в_обогащение(_найти(cfg), для_обогащения)
    print("в enrich.db:", n)
except Exception as ex:                                        # noqa: BLE001
    print("enrich.db не принял вердикты:", str(ex)[:110])

try:
    con = sqlite3.connect(ОБЗВОН, timeout=30)
    con.execute("CREATE TABLE IF NOT EXISTS email_probe ("
                "email TEXT PRIMARY KEY, verdict TEXT, source TEXT, "
                "answer TEXT, ts TEXT)")
    сейчас = datetime.now(timezone.utc).isoformat()
    con.executemany(
        "INSERT INTO email_probe(email, verdict, source, answer, ts) "
        "VALUES(?,?,?,?,?) ON CONFLICT(email) DO UPDATE SET "
        "verdict=excluded.verdict, source=excluded.source, "
        "answer=excluded.answer, ts=excluded.ts",
        [(v["email"], v["verdict"], "проба с сервера",
          str(v.get("answer") or "")[:200], сейчас) for v in для_обогащения])
    con.commit()
    con.close()
    print("в obzvon-index.db:", len(для_обогащения))
except Exception as ex:                                        # noqa: BLE001
    print("obzvon-index не принял вердикты:", str(ex)[:110])

осталось = [e for e in адрес_кому if not кэш.cached(e)]
print(f"\nосталось без вердикта: {len(осталось)} "
      f"(повторный запуск продолжит с них)")
