# -*- coding: utf-8 -*-
"""Работник проверки адресов для отдельного VPS.

Живёт НЕ на боевом сервере: у него свой IP, своя обратная запись, и если
антиспам-списки его когда-нибудь заметят, панель, дроп, сервер отписки и
рассылка этого не почувствуют. Решение владельца 07.08: «безопасность в
первую очередь».

Как устроен обмен — через тот же дроп, никаких прямых доступов между
машинами:

    probe-zadanie.json    <- панель кладёт адреса на проверку
    probe-rezultat.jsonl  -> работник дописывает вердикты (durable, с fsync)

Логика вердиктов — ровно та же, что в панели (sender/addr_probe.py):
адрес хоронит ТОЛЬКО явное «такого пользователя нет». Отказ самой пробе
(нужен TLS, нет PTR, серый список) — это про нас, а не про адрес.

Запуск на VPS:
    python3 probe_worker.py                 # один проход
    python3 probe_worker.py --demon 600     # каждые 10 минут

Переменные окружения: DROP_URL, DROP_TOKEN, PROBE_HELO, PROBE_MAIL_FROM.
"""
import argparse
import json
import os
import re
import smtplib
import socket
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone

ЗАДАНИЕ = "probe-zadanie.json"
РЕЗУЛЬТАТ = "probe-rezultat.jsonl"
МЕСТНЫЙ = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "probe-rezultat.jsonl")

_МЁРТВ = ("no such user", "user unknown", "unknown user", "user not found",
          "no such recipient", "recipient not found", "invalid mailbox",
          "mailbox unavailable", "mailbox not found", "mailbox does not exist",
          "address does not exist", "no mailbox",
          "recipient address rejected: user", "нет такого пользователя",
          "пользователь не найден", "почтовый ящик не найден")
_ПРО_ПРОБУ = ("encryption is required", "starttls", "ptr", "reverse",
              "hostname", "verification failed", "spf", "dmarc", "greylist",
              "try again", "policy", "blocked", "blacklist", "access denied",
              "not permitted", "rejected: message", "ip name lookup", "relay",
              "too many", "rate")
_МЁРТВЫЙ_КОД = re.compile(r"\b5\.1\.[01]\b")
# Домен принимает ЛЮБОЙ адрес. Проверяется вопросом про выдуманный ящик: если
# сервер и на него говорит «приму», его «приму» про настоящий адрес не значит
# ничего. Поймано 11.08 живой отбивкой: kk@vebfabrika.ru проба назвала живым,
# письмо вернулось «invalid mailbox. Local mailbox is unavailable».
ПРИНИМАЕТ_ВСЁ = "принимает всё"
_CATCH_КЭШ = {}


def классифицировать(код, ответ):
    низ = (ответ or "").lower()
    if код is not None and 200 <= код < 300:
        return "есть"
    if код is not None and 500 <= код < 600:
        if any(m in низ for m in _МЁРТВ) or _МЁРТВЫЙ_КОД.search(низ):
            return "нет ящика"
        if any(m in низ for m in _ПРО_ПРОБУ):
            return "отказ пробе"
    return "неясно"


def дроп(метод, имя, данные=None):
    база = os.environ["DROP_URL"].rstrip("/")
    з = urllib.request.Request(f"{база}/{имя}", data=данные, method=метод)
    з.add_header("X-Drop-Token", os.environ["DROP_TOKEN"])
    with urllib.request.urlopen(з, timeout=90) as о:
        return о.read()


_MX_КЭШ = {}


def mx_for(домен):
    if домен in _MX_КЭШ:
        return _MX_КЭШ[домен]
    хост = None
    try:
        import dns.resolver  # type: ignore
        о = dns.resolver.resolve(домен, "MX", lifetime=8)
        хост = sorted((r.preference, str(r.exchange).rstrip(".")) for r in о)[0][1]
    except Exception:  # noqa: BLE001 - без dnspython спрашиваем систему
        # ВАЖНО: работник живёт на Windows, где dig не поставляется. Первая
        # редакция звала dig, он не находился, и работник честно писал «нет MX»
        # ПО ВСЕМ адресам подряд. Спрашиваем nslookup — он есть всегда.
        try:
            import subprocess
            out = subprocess.run(["nslookup", "-type=MX", домен],
                                 capture_output=True, text=True, timeout=20,
                                 errors="replace").stdout
            # Разбор НЕ привязан к английским словам: русская Windows пишет
            # «почтовый обменник» вместо «mail exchanger», и жёсткая регулярка
            # снова дала бы «нет MX» по всем адресам. Опираемся на форму строки
            # «… = <число>, … = <хост>» — она одна во всех локалях.
            пары = re.findall(r"=\s*(\d+)\s*,\s*[^=\n]*=\s*(\S+)", out)
            if пары:
                хост = sorted((int(p), h) for p, h in пары)[0][1].rstrip(".")
            else:
                м = re.findall(r"=\s*([A-Za-z0-9][-A-Za-z0-9.]*\.[A-Za-z]{2,})",
                               out)
                хост = м[-1].rstrip(".") if м else None
        except Exception:  # noqa: BLE001
            хост = None
    _MX_КЭШ[домен] = хост
    return хост


def принимает_всё(домен, helo, mail_from, пауза, таймаут=15):
    """Отвечает ли домен «приму» на заведомо несуществующий ящик.

    Спрашиваем ОДИН раз на домен: домены в базе повторяются, а лишние
    разговоры с чужим сервером ни к чему.
    """
    if домен in _CATCH_КЭШ:
        return _CATCH_КЭШ[домен]
    выдумка = f"nesushchestvuyushchiy-{uuid.uuid4().hex[:12]}@{домен}"
    з = _разговор(выдумка, helo, mail_from, пауза, таймаут)
    вердикт = классифицировать(з[0], з[1])
    ответ = True if вердикт == "есть" else (False if вердикт == "нет ящика" else None)
    _CATCH_КЭШ[домен] = ответ
    return ответ


def _разговор(адрес, helo, mail_from, пауза, таймаут):
    """Один разговор до RCPT TO: (код, ответ). Письмо не отправляется."""
    домен = адрес.rsplit("@", 1)[-1]
    хост = mx_for(домен)
    if not хост:
        return None, "у домена нет MX-записи"
    time.sleep(пауза)
    код, ответ = None, ""
    try:
        with smtplib.SMTP(хост, 25, timeout=таймаут,
                          local_hostname=helo or None) as s:
            s.ehlo_or_helo_if_needed()
            try:
                if s.has_extn("starttls"):
                    s.starttls()
                    s.ehlo()
            except Exception:  # noqa: BLE001
                pass
            s.mail(mail_from or "")
            код, сырой = s.rcpt(адрес)
            ответ = (сырой or b"").decode("utf-8", "replace")
    except UnicodeEncodeError:
        ответ = "адрес не-ASCII, проба неприменима"
    except Exception as e:  # noqa: BLE001
        ответ = str(e)[:150]
    return код, ответ


def проверить(адрес, helo, mail_from, пауза, таймаут=15):
    домен = адрес.rsplit("@", 1)[-1]
    хост = mx_for(домен)
    если_нет = {"email": адрес, "verdict": "нет MX", "code": None,
                "answer": "у домена нет MX-записи", "mx": None,
                "ts": datetime.now(timezone.utc).isoformat()}
    if not хост:
        return если_нет
    код, ответ = _разговор(адрес, helo, mail_from, пауза, таймаут)
    вердикт = классифицировать(код, ответ)
    if вердикт == "есть" and принимает_всё(домен, helo, mail_from, пауза, таймаут):
        вердикт = ПРИНИМАЕТ_ВСЁ
        ответ = (ответ + " | домен принимает любой адрес").strip()
    return {"email": адрес, "verdict": вердикт,
            "code": код, "answer": ответ[:200], "mx": хост,
            "ts": datetime.now(timezone.utc).isoformat()}


def проход(пауза, на_домен, лимит):
    try:
        сырое = дроп("GET", ЗАДАНИЕ)
        адреса = json.loads(сырое.decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        print(f"задания нет или не читается: {str(e)[:90]}")
        return 0
    if isinstance(адреса, dict):
        адреса = адреса.get("emails") or []
    сделано = set()
    if os.path.exists(МЕСТНЫЙ):
        for с in open(МЕСТНЫЙ, encoding="utf-8"):
            try:
                сделано.add(json.loads(с)["email"])
            except Exception:  # noqa: BLE001
                pass
    очередь = [str(a).strip().lower() for a in адреса
               if a and "@" in str(a) and str(a).strip().lower() not in сделано]
    print(f"в задании {len(адреса)}, к проверке {len(очередь)}")
    helo = os.environ.get("PROBE_HELO", "")
    mail_from = os.environ.get("PROBE_MAIL_FROM", "")
    счёт_домена = {}
    сделано_сейчас = 0
    with open(МЕСТНЫЙ, "a", encoding="utf-8") as поток:
        for адрес in очередь[:лимит]:
            домен = адрес.rsplit("@", 1)[-1]
            if счёт_домена.get(домен, 0) >= на_домен:
                continue                      # бережём и чужой сервер, и себя
            счёт_домена[домен] = счёт_домена.get(домен, 0) + 1
            з = проверить(адрес, helo, mail_from, пауза)
            поток.write(json.dumps(з, ensure_ascii=False) + "\n")
            поток.flush()
            os.fsync(поток.fileno())
            сделано_сейчас += 1
            print(f"   {адрес:38} {з['verdict']:12} {str(з.get('code') or '')}")
    if сделано_сейчас:
        with open(МЕСТНЫЙ, "rb") as f:
            дроп("PUT", РЕЗУЛЬТАТ, f.read())
        print(f"результат выложен на дроп: {сделано_сейчас} новых")
    return сделано_сейчас


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--demon", type=int, default=0,
                   help="работать постоянно, пауза между проходами (сек)")
    p.add_argument("--pause", type=float, default=3.0,
                   help="пауза между пробами, сек (щадит чужие серверы и наш IP)")
    p.add_argument("--per-domain", type=int, default=3,
                   help="сколько адресов одного домена за проход")
    p.add_argument("--limit", type=int, default=200,
                   help="сколько адресов за один проход")
    a = p.parse_args()
    for ключ in ("DROP_URL", "DROP_TOKEN"):
        if not os.environ.get(ключ):
            print(f"нет переменной {ключ}")
            return 2
    if not a.demon:
        проход(a.pause, a.per_domain, a.limit)
        return 0
    while True:
        try:
            проход(a.pause, a.per_domain, a.limit)
        except Exception as e:  # noqa: BLE001 - проход упал, работник живёт
            print(f"проход упал: {str(e)[:120]}")
        time.sleep(a.demon)


if __name__ == "__main__":
    sys.exit(main() or 0)
