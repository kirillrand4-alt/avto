# -*- coding: utf-8 -*-
"""Перепроверка доменов на «принимает всё» — разовый прогон на проверочном VPS.

Зачем. Проба спрашивает у сервера получателя, есть ли такой ящик, и «приму»
считает подтверждением. 11.08 живая отбивка показала цену этого допущения:
kk@vebfabrika.ru проба назвала живым, письмо вернулось «invalid mailbox. Local
mailbox is unavailable». Домен отвечает «приму» кому угодно, и его «приму» не
значит ничего.

Новая проба ловит это сама на каждом адресе. А те 346 адресов, что уже лежат
в базе с вердиктом «есть», проверены СТАРОЙ пробой — их надо переспросить.
Спрашиваем по домену, а не по адресу: один выдуманный ящик на домен даёт
ответ сразу по всем его адресам.

Запуск (через vps_runner, задача py):
    python catchall_sweep.py [--limit 400] [--pause 3]

Обмен через дроп:
    catchall-zadanie.json    <- панель кладёт домены
    catchall-rezultat.jsonl  -> сюда дописываются вердикты (с fsync)

Резюмируемость обязательна: прогон идёт минуты, VPS может уйти в перезагрузку,
а начинать 250 разговоров заново — лишний след с нашего IP. Уже проверенные
домены читаются из местного файла и пропускаются.
"""
import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

# Раннер кладёт присланный скрипт в подпапку _ops, а probe_worker.py лежит
# этажом выше, рядом с самим раннером. Ищем в обоих местах: без этого прогон
# падает на импорте, а падает он уже НА VPS, где отладка стоит круга обмена.
_ЗДЕСЬ = os.path.dirname(os.path.abspath(__file__))
for _путь in (_ЗДЕСЬ, os.path.dirname(_ЗДЕСЬ)):
    if _путь not in sys.path:
        sys.path.insert(0, _путь)
from probe_worker import (_разговор, дроп, классифицировать,  # noqa: E402
                          mx_for)

ЗАДАНИЕ = "catchall-zadanie.json"
РЕЗУЛЬТАТ = "catchall-rezultat.jsonl"
МЕСТНЫЙ = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "catchall-rezultat.jsonl")


def проверить_домен(домен, helo, mail_from, пауза, таймаут=15):
    """Отвечает ли домен «приму» на заведомо несуществующий ящик.

    Три исхода, и третий важен не меньше первых двух:
      принимает всё — «приму» этого домена ничего не подтверждает;
      честный      — умеет отказывать, значит его «есть» настоящее;
      неясно       — сервер отказал нашей пробе; про домен мы не узнали ничего
                     и врать в базу об этом не будем.
    """
    хост = mx_for(домен)
    сейчас = datetime.now(timezone.utc).isoformat()
    if not хост:
        return {"domen": домен, "itog": "нет MX", "code": None,
                "answer": "у домена нет MX-записи", "mx": None, "ts": сейчас}
    выдумка = f"nesushchestvuyushchiy-{uuid.uuid4().hex[:12]}@{домен}"
    код, ответ = _разговор(выдумка, helo, mail_from, пауза, таймаут)
    вердикт = классифицировать(код, ответ)
    итог = ("принимает всё" if вердикт == "есть" else
            "честный" if вердикт == "нет ящика" else "неясно")
    return {"domen": домен, "itog": итог, "code": код,
            "answer": (ответ or "")[:200], "mx": хост, "ts": сейчас}


def прогон(пауза, лимит, таймаут):
    сырое = дроп("GET", ЗАДАНИЕ)
    домены = json.loads(сырое.decode("utf-8", "replace"))
    if isinstance(домены, dict):
        домены = домены.get("domeny") or []
    сделано = {}
    if os.path.exists(МЕСТНЫЙ):
        for с in open(МЕСТНЫЙ, encoding="utf-8"):
            try:
                з = json.loads(с)
                сделано[з["domen"]] = з["itog"]
            except Exception:  # noqa: BLE001 - битая строка не рвёт прогон
                pass
    очередь = [str(d).strip().lower() for d in домены
               if d and "." in str(d) and str(d).strip().lower() not in сделано]
    print(f"в задании {len(домены)}, уже проверено {len(сделано)}, "
          f"к проверке {len(очередь)}")

    helo = os.environ.get("PROBE_HELO", "")
    mail_from = os.environ.get("PROBE_MAIL_FROM", "")
    свод = {}
    with open(МЕСТНЫЙ, "a", encoding="utf-8") as поток:
        for домен in очередь[:лимит]:
            з = проверить_домен(домен, helo, mail_from, пауза, таймаут)
            поток.write(json.dumps(з, ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
            свод[з["itog"]] = свод.get(з["itog"], 0) + 1
            print(f"   {домен:34} {з['itog']:14} {str(з.get('code') or '')}")
    # Выкладываем ВЕСЬ накопленный файл, а не прирост: панель забирает его
    # целиком и разбирает построчно, порядок и повторы ей не мешают.
    with open(МЕСТНЫЙ, "rb") as f:
        дроп("PUT", РЕЗУЛЬТАТ, f.read())
    осталось = max(0, len(очередь) - лимит)
    print(f"свод: {свод} | осталось на следующий заход: {осталось}")
    return {"проверено": sum(свод.values()), "свод": свод, "осталось": осталось}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=400)
    p.add_argument("--pause", type=float, default=3.0,
                   help="пауза перед каждым разговором, сек")
    p.add_argument("--timeout", type=float, default=15.0)
    a = p.parse_args()
    for ключ in ("DROP_URL", "DROP_TOKEN"):
        if not os.environ.get(ключ):
            print(f"нет переменной {ключ}")
            return 2
    начало = time.time()
    итог = прогон(a.pause, a.limit, a.timeout)
    print(f"заняло {time.time() - начало:.0f}с")
    print(json.dumps(итог, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
