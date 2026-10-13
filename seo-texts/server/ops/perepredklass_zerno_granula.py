# -*- coding: utf-8 -*-
"""Перепроверка решений «кц»/«никуда» предклассификатора по двум новым правилам
владельца 13.10: (1) зерно - не только переработка: хозяйства с ЗАВ/сушилкой/
складом/лабораторией/тысячами га, элеваторы, трейдеры, терминалы перевалки зерна;
(2) пластик - ещё и производители гранулы, компаундов, мастербатчей, ПЭТ-преформ
на вторичных хлопьях.

Кандидаты - по ВСЕМ отраслям книги, где в паспорте есть зерно/масличные или
гранула. Промпт - текущий _ПРЕДКЛАСС_СИСТЕМА из partiya_gen.py. Решения - в
verdikty_v_bazy (обе базы) и в журнал предкласса (последняя строка по ИНН
главная), плюс свой журнал _ops/perepredklass-13-10.jsonl (fsync).

    perepredklass_zerno_granula.py            — сколько и по каким отраслям
    perepredklass_zerno_granula.py --zapusk   — в фоне (+ перезапуск полного прогона на новом промпте)
    perepredklass_zerno_granula.py --hod      — итог: кто перешёл в Meyer
"""
import ast
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("PROVIDER_THINKING_FIELD", "omit")
ОПС = r"C:\sender\server\ops"
ЖУР_ПК = r"C:\sender\_ops\predklass-vsey-bazy.jsonl"
ЖУР = r"C:\sender\_ops\perepredklass-13-10.jsonl"
ЛОГ = r"C:\sender\_ops\perepredklass-13-10.log"
ЗЕРНО = re.compile(r"пшениц|ячмен|зерн|кукуруз|подсолнечн|(?<![а-яё])со[яи](?![а-яё])|рапс|горох|ов[её]с|"
                   r"(?<![а-яё])рож[ьи]|гречих|(?<![а-яё])просо|чечевиц|масличн|бобов|элеватор|зерносуш", re.I)
ГРАНУЛА = re.compile(r"гранул|компаунд|концентрат|мастербатч|преформ|флекс|хлопь|рецикл|"
                     r"вторичн\w*\s+(?:полимер|пластик|пэт|сырь)", re.I)
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
сег, имя = {}, {}
for inn, s, n in c.execute("SELECT inn, segment, company_name FROM recipients WHERE inn IS NOT NULL"):
    сег["".join(ч for ч in str(inn) if ч.isdigit())] = s or ""
    имя["".join(ч for ч in str(inn) if ч.isdigit())] = n or ""

if "--hod" in sys.argv:
    до, после = {}, {}
    for с in io.open(ЖУР, encoding="utf-8") if os.path.exists(ЖУР) else []:
        з = json.loads(с)
        до[з["inn"]] = з["bylo"]
        после[з["inn"]] = з["napr"]
    пер = Counter("%s→%s" % (до[i], после[i]) for i in после)
    print("перепроверено: %d; %s" % (len(после), dict(пер.most_common())))
    в_мейер = defaultdict(list)
    for i in после:
        if после[i] in ("мейер", "оба") and до[i] not in ("мейер", "оба"):
            в_мейер[сег.get(i, "?")].append(i)
    for s, сп in sorted(в_мейер.items(), key=lambda x: -len(x[1])):
        print("  в Meyer из «%s»: %d — %s" % (s[:30], len(сп), "; ".join(имя.get(i, "")[:28] for i in сп[:6])))
    try:
        print("лог: " + io.open(ЛОГ, encoding="utf-8", errors="replace").read()[-250:])
    except Exception:  # noqa: BLE001
        pass
    print("=== ПЕРЕПРОВЕРКА: ХОД ===")
    sys.exit(0)

if "--zapusk" in sys.argv:
    # полный прогон держит промпт в памяти со старта — перезапускаем, он продолжит с места
    убито = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*predklass_vsey_bazy*--rabota*' }"
                            " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; $_.ProcessId }"],
                           capture_output=True, text=True, timeout=60).stdout.split()
    print("полный прогон остановлен: %s" % (убито or "не шёл"))
    if убито:
        subprocess.run([sys.executable, os.path.join(ОПС, "predklass_vsey_bazy.py"), "--zapusk"], cwd=r"C:\sender", timeout=60)
    п = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--rabota"], cwd=r"C:\sender",
                         stdout=io.open(ЛОГ, "w"), stderr=subprocess.STDOUT, creationflags=0x00000008 | 0x00000200)
    time.sleep(8)
    print("перепроверка запущена, pid %d, жив %s" % (п.pid, п.poll() is None))
    print("=== ПЕРЕПРОВЕРКА: ЗАПУЩЕНА ===")
    sys.exit(0)

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
sys.path.insert(0, ОПС)
from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.ai_quota import build_ai_quota  # noqa: E402
cfg = Config.load(r"C:\sender\sender.yaml")
q = build_ai_quota(Store(cfg.get("service.db_path", r"C:\sender\sender.db")), cfg)


def паспорт(инн):
    try:
        d = q._site_facts(инн) or {}
    except Exception:  # noqa: BLE001
        return ""
    куски = []
    for k in ("цитата", "продукция", "оборудование_линии", "сырьё", "масштаб", "мощности"):
        v = d.get(k)
        if v:
            куски.append(f"{k}: " + (v if isinstance(v, str) else "; ".join(map(str, v))[:260]))
    return "\n".join(куски)[:1200]


реш = {}
for с in io.open(ЖУР_ПК, encoding="utf-8"):
    з = json.loads(с)
    реш[з["inn"]] = з["napr"]
готово = set()
if os.path.exists(ЖУР):
    for с in io.open(ЖУР, encoding="utf-8"):
        готово.add(json.loads(с)["inn"])
канд, св = [], Counter()
for инн, н in реш.items():
    if н not in ("кц", "никуда") or инн in готово:
        continue
    п = паспорт(инн)
    if not п:
        continue
    з, г = bool(ЗЕРНО.search(п)), bool(ГРАНУЛА.search(п))
    if not (з or г):
        continue
    св[("зерно" if з else "") + ("+" if з and г else "") + ("гранула" if г else "")] += 1
    св["отрасль: " + (сег.get(инн) or "?")[:26]] += 1
    канд.append((инн, имя.get(инн, ""), п, н))
print("решено предклассом: %d, из них кц/никуда с зерном или гранулой в паспорте: %d (уже перепроверено %d)"
      % (len(реш), len(канд), len(готово)))
for k, v in sorted(св.items(), key=lambda x: (not x[0].startswith(("зерно", "гранула")), -x[1]))[:22]:
    print("  %s: %d" % (k, v))
if "--rabota" not in sys.argv:
    print("=== ПЕРЕПРОВЕРКА: СУХОЙ ПРОГОН ===")
    sys.exit(0)

import gen_provider  # noqa: E402
import verdikty_v_bazy as вб  # noqa: E402
исх = io.open(os.path.join(ОПС, "partiya_gen.py"), encoding="utf-8").read()
СИСТЕМА = next(ast.literal_eval(у.value) for у in ast.parse(исх).body
               if isinstance(у, ast.Assign) and getattr(у.targets[0], "id", "") == "_ПРЕДКЛАСС_СИСТЕМА")
assert "ЗЕРНО - НЕ ТОЛЬКО ПЕРЕРАБОТКА" in СИСТЕМА and "ИЛИ производитель гранулы" in СИСТЕМА, "промпт старый"
замок = threading.Lock()


def пачка(кусок):
    блоки = [f"ИНН {a} · {b}\n{p}" for a, b, p, _ in кусок]
    д = {}
    for попытка in range(3):
        try:
            m = gen_provider._raw_stream([{"role": "user", "content": "Компании:\n\n" + "\n\n".join(блоки)}],
                                         "claude-sonnet-4-6", 8000, thinking=False, system=СИСТЕМА)
            т = "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
            мм = re.search(r"\{.*\}", т, re.S)
            д = json.loads(мм.group(0)) if мм else {}
            if not д.get("firmy"):
                raise ValueError("пустой разбор")
            break
        except Exception as е:  # noqa: BLE001
            д = {}
            print("пачка: попытка %d: %s" % (попытка + 1, str(е)[:80]), flush=True)
            time.sleep(10)
    было = {a: н for a, _, _, н in кусок}
    записи = []
    for v in д.get("firmy") or []:
        инн = "".join(ч for ч in str(v.get("inn") or "") if ч.isdigit())
        н = str(v.get("napravlenie") or "").strip().lower()
        if инн in было and н:
            записи.append({"inn": инн, "napr": н, "istochnik": "предкласс",
                           "rusprom": "не покупатель" if н == "никуда" else None,
                           "pochemu": "предклассификатор, перепроверка 13.10 (зерно/гранула)"})
    with замок:
        вб.obnovit(записи)
        for путь, дать in ((ЖУР_ПК, lambda з: {"inn": з["inn"], "napr": з["napr"]}),
                           (ЖУР, lambda з: {"inn": з["inn"], "napr": з["napr"], "bylo": было[з["inn"]]})):
            with io.open(путь, "a", encoding="utf-8") as ж:
                for з in записи:
                    ж.write(json.dumps(дать(з), ensure_ascii=False) + "\n")
                ж.flush()
                os.fsync(ж.fileno())
    print("пачка: %d → %s" % (len(кусок), dict(Counter(з["napr"] for з in записи))), flush=True)


куски = [канд[i:i + 15] for i in range(0, len(канд), 15)]
with ThreadPoolExecutor(3) as пул:
    list(пул.map(пачка, куски))
print("готово", flush=True)
