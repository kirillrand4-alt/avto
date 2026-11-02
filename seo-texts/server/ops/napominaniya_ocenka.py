# -*- coding: utf-8 -*-
"""Оценка напоминаний моделью провайдера (владелец 02.11: «отправь штук 50 писем
на проверку провайдеру»): на это хочется ответить? приведёт к покупке? грамотно ли
(технические, орфографические, филологические ошибки)? Случайные pending-карточки
из _ops/napominaniya-v2.jsonl, одной пачкой до 50. Итог — _ops/napominaniya-ocenka.txt
и на дроп. Писем не трогает.
    napominaniya_ocenka.py [N=50]"""
import io, json, os, random, re, sqlite3, sys
import requests
sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402
N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
МОДЕЛЬ = "claude-sonnet-4-6"
з = [json.loads(s) for s in io.open(r"C:\sender\_ops\napominaniya-v2.jsonl", encoding="utf-8")]
c = sqlite3.connect("file:C:\\sender\\sender.db?mode=ro", uri=True, timeout=30)
з = [x for x in з if x.get("karta") and (c.execute("SELECT status FROM confirm_reviews WHERE id=?", (x["karta"],)).fetchone() or [""])[0] == "pending"]
random.seed(2)
выб = random.sample(з, min(N, len(з)))
ЗАДАНИЕ = """Ты - опытный закупщик/технолог российского пищевого производства и одновременно
литературный редактор. Тебе пришли письма-напоминания от поставщика оборудования
(фотосепараторы и рентген-инспекция Meyer). Это повторное письмо в ветку первого,
на которое компания не ответила. Оцени КАЖДОЕ честно и строго, как реальный получатель.

По каждому письму ответь:
1) ОТВЕТИТЬ: хочется ли на это ответить? оценка 1-5 и одна фраза почему;
2) ПОКУПКА: насколько это письмо приближает к покупке? оценка 1-5 и одна фраза почему;
3) ГРАМОТНОСТЬ: есть ли технические, орфографические, пунктуационные, стилистические
   (филологические) ошибки? Выпиши каждую ошибку цитатой и как исправить; нет ошибок - «нет».

Формат ответа строго такой, без вступлений:
=== N
ОТВЕТИТЬ: <1-5> - <почему>
ПОКУПКА: <1-5> - <почему>
ГРАМОТНОСТЬ: <ошибки или «нет»>

{pisma}

В конце после всех писем дай блок
=== ИТОГ
<3-6 строк: общие сильные и слабые стороны и что поменять в шаблоне>"""
вых, цифры = [], {"о": [], "п": []}
for i in range(0, len(выб), 50):   # шлюз режет запросы короче 10k токенов (429) — пачки крупнее
    пачка = выб[i:i + 50]
    тексты = ["ПИСЬМО %d (кому: %s; тема: %s)\n%s" % (k, x["email"], x["tema"], x["telo"]) for k, x in enumerate(пачка, 1)]
    m = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ.replace("{pisma}", "\n\n---\n\n".join(тексты))}],
                       МОДЕЛЬ, 24000, thinking=False, effort="low")
    т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
    for k, x in enumerate(пачка, 1):
        б = re.search(r"===\s*%d\s*\n(.*?)(?=\n===|\Z)" % k, т, re.S)
        оц = б.group(1).strip() if б else "(нет ответа)"
        for ключ, сп in (("ОТВЕТИТЬ", "о"), ("ПОКУПКА", "п")):
            мм = re.search(ключ + r":\s*(\d)", оц)
            if мм:
                цифры[сп].append(int(мм.group(1)))
        вых.append("=" * 70 + "\n#%s | шаблон %s | %s | %s\n\n%s\n\n--- ОЦЕНКА\n%s" % (x["karta"], x["zahod"], x["email"], x["tema"], x["telo"], оц))
    и = re.search(r"===\s*ИТОГ\s*\n(.*)", т, re.S)
    вых.append("#" * 70 + "\nИТОГ ПАЧКИ %d\n%s" % (i // 50 + 1, и.group(1).strip() if и else "(нет)"))
    print("пачка %d готова" % (i // 50 + 1), flush=True)
ср = lambda a: (sum(a) / len(a)) if a else 0
шапка = "Оценено писем: %d | хочется ответить: ср. %.1f из 5 | приведёт к покупке: ср. %.1f из 5\n" % (len(выб), ср(цифры["о"]), ср(цифры["п"]))
текст = шапка + "\n\n".join(вых) + "\n"
io.open(r"C:\sender\_ops\napominaniya-ocenka.txt", "w", encoding="utf-8").write(текст)
try:
    requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/napominaniya-ocenka.txt",
                 data=текст.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
except Exception as ex:  # noqa: BLE001
    print("на дроп не ушло:", ex)
print(шапка)
