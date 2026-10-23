# -*- coding: utf-8 -*-
"""Заходы напоминания Meyer «через ценность» (владелец 23.10: «мне нравится ход
твоих мыслей про ценность, закинь на провайдера образцы писем наших, пусть свои
идеи тоже накидают, через что ещё можно заходить»).

Берём 5 реально отправленных писем Meyer разных отраслей (confirm_reviews.body),
даём моделям принцип «напоминание даёт пользу, а не просит ответа» и список
того, что у нас реально есть. Каждая модель — 15 заходов: идея + фраза.
Итог — _ops/zahody-cennost.txt и на дроп (тот же файл).
    zahody_cennost.py [модель,модель,...]"""
import io
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.insert(0, r"C:\sender")
sys.path.insert(0, r"C:\sender\server")
import gen_provider as GP  # noqa: E402

МОДЕЛИ = (sys.argv[1].split(",") if len(sys.argv) > 1 else
          ["claude-opus-4-8", "claude-opus-4-6", "claude-fable-5", "claude-sonnet-4-6"])

c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
кам = [r[0] for r in c.execute("SELECT id, name FROM campaigns") if "meyer" in str(r[1]).lower()]
q = ",".join("?" * len(кам))
письма, отрасли = [], set()
for тема, тело, okved in c.execute(
        "SELECT cr.subject, cr.body, coalesce(r.okved,'') FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
        "JOIN recipients r ON r.id=m.recipient_id WHERE m.campaign_id IN (%s) AND m.status='sent' "
        "AND length(cr.body) > 300 ORDER BY m.id DESC LIMIT 3000" % q, кам):
    о = str(okved)[:2]
    if о in отрасли:
        continue
    отрасли.add(о)
    письма.append("Тема: %s\n%s" % (тема, тело.split("\n\nС уважением,")[0].strip()))
    if len(письма) >= 5:
        break
c.close()

ЗАДАНИЕ = """Мы — Meyer (направление ООО «Руспром»): фотосепараторы (сортировка зерна,
круп, орехов, семян, пластика, минералов по цвету/форме) и рентген-инспекция
(поиск стекла, камня, металла, костей в продукции и упаковке).

Ниже — наши реальные первые холодные письма производственным компаниям. На многие
ответа нет, прошло 2-4 недели, письмо могло попасть в спам. Мы отправим КОРОТКОЕ
напоминание В ТУ ЖЕ ВЕТКУ (Re: та же тема) с того же ящика.

Слабые напоминания, которые у нас уже есть, только ПРОСЯТ: «актуально?», «да/нет?»,
«кому переслать?». Человеку незачем отвечать. Нам нужны заходы, которые ДАЮТ
ценность или задают лёгкий, интересный для него вопрос про его производство.

ЧТО У НАС РЕАЛЬНО ЕСТЬ (опираться можно только на это):
- бесплатная тестовая сортировка образца сырья клиента на нашем сепараторе;
- видео с тестовой сортировки по культурам/материалам;
- расчёт производительности и цены под объём клиента;
- короткий звонок с инженером;
- рентген-проверка образцов упакованной продукции.

Уже придуманы (не повторяй их, придумай ДРУГИЕ заходы): бесплатный прогон образца с
видео; «что мешает в сырье: камни, сор, цвет»; «перебираете вручную или машиной?»;
прикинуть цену под тонны в час; «кто отвечает за качество на входе»; «брак устраивает?»;
«напишу к сезону»; «пришлю видео по вашей культуре»; «10 минут звонка»; «ответьте нет — не буду писать».

Придумай 15 НОВЫХ, разных по сути заходов. Требования к фразе:
- 1-3 коротких предложения, живой менеджер, без канцелярита и без давления;
- можно подставлять {сырьё}, {продукция}, {культура}, {отрасль} — мы заполним из карточки;
- НЕ выдумывать факты о компании и отрасли («видел, что вы расширяетесь», «в отрасли
  штрафуют», «требования ужесточили» — нельзя), без цифр, цен, ссылок, имён клиентов;
- без длинного тире (только дефис или запятая), без подписи, без «надеюсь, всё хорошо».

НАШИ ПИСЬМА:
{письма}

Ответ - СТРОГО JSON без пояснений:
{{"zahody": [{{"ideya": "в чём заход, 3-8 слов", "fraza": "текст напоминания"}}]}}"""


def один(модель):
    try:
        m = GP._raw_stream([{"role": "user", "content": ЗАДАНИЕ.replace("{письма}", "\n\n---\n\n".join(письма)).replace("{{", "{").replace("}}", "}")}],
                           модель, 4000, thinking=False, effort="low")
        т = m if isinstance(m, str) else "".join(getattr(b, "text", "") for b in getattr(m, "content", []) or [])
        д, _ = json.JSONDecoder(strict=False).raw_decode(т[т.find("{"):])
        return модель, д.get("zahody") or [], None
    except Exception as ex:  # noqa: BLE001
        return модель, [], str(ex)[:200]


with ThreadPoolExecutor(max_workers=len(МОДЕЛИ)) as пул:
    итоги = list(пул.map(один, МОДЕЛИ))
вых = ["Образцов писем дано моделям: %d" % len(письма)]
for модель, заходы, ош in итоги:
    вых.append("\n--- %s: %s" % (модель, "сбой: " + ош if ош else "%d заходов" % len(заходы)))
    for i, з in enumerate(заходы, 1):
        вых.append("%2d. [%s] %s" % (i, re.sub(r"\s+", " ", str(з.get("ideya", ""))).strip(),
                                    re.sub(r"\s+", " ", str(з.get("fraza", ""))).strip()))
вых.append("\n\n" + "=" * 70 + "\nОБРАЗЦЫ ПИСЕМ\n" + "=" * 70 + "\n\n" + "\n\n---\n\n".join(письма))
текст = "\n".join(вых) + "\n"
п = r"C:\sender\_ops\zahody-cennost.txt"
io.open(п, "w", encoding="utf-8").write(текст)
try:
    requests.put(os.environ.get("DROP_URL", "https://parsercompressor.online/drop").rstrip("/") + "/zahody-cennost.txt",
                 data=текст.encode("utf-8"), headers={"X-Drop-Token": os.environ.get("DROP_TOKEN", "")}, timeout=60)
except Exception as ex:  # noqa: BLE001
    print("на дроп не ушло:", ex)
print(текст[:200])
for модель, заходы, ош in итоги:
    print(модель, ош or len(заходы))
