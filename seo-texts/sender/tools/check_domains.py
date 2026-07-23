#!/usr/bin/env python3
"""Префлайт доменов рассылки: DNS (MX/SPF/DKIM/DMARC) + редирект корня.

Читает реестр `sender/config/domains.json` и для каждого домена сверяет
записи с ожиданиями его почтового хостинга (Яндекс 360 / VK WorkSpace):

  ya360:  MX mx.yandex.net,  SPF _spf.yandex.net,  DKIM mail._domainkey
  vkws:   MX emx.mail.ru,    SPF _spf.mail.ru,     DKIM mailru._domainkey
  оба:    _dmarc с v=DMARC1; редирект корня на целевой сайт (https)

Резолвинг — DNS-over-HTTPS (dns.google) через curl: работает и из песочницы
за прокси, и с боевого сервера; системный резолвер не нужен. Панельный
DnsHealth (dns.py) остаётся для рантайма — это именно ПРЕФЛАЙТ перед закупкой
ящиков/прогревом, отсюда и проверка редиректа, которой в панели нет.

Запуск:  python3 sender/tools/check_domains.py [--json report.json] [домен ...]
Код выхода 1, если хоть у одного домена есть проблемы.
"""

import argparse
import json
import os
import subprocess
import sys

REGISTRY = os.path.join(os.path.dirname(__file__), "..", "config", "domains.json")

EXPECT = {
    "ya360": {"mx": "mx.yandex.net", "spf": "_spf.yandex.net", "dkim_sel": "mail",
              "title": "Яндекс 360"},
    "vkws": {"mx": "emx.mail.ru", "spf": "_spf.mail.ru", "dkim_sel": "mailru",
             "title": "VK WorkSpace"},
}


def doh(name: str, rtype: str):
    """DNS-over-HTTPS. Возвращает (dns-status, [data,...]); -1 = сеть не ответила."""
    for _ in range(3):
        try:
            out = subprocess.run(
                ["curl", "-sS", "--max-time", "15",
                 f"https://dns.google/resolve?name={name}&type={rtype}"],
                capture_output=True, text=True, timeout=20)
            j = json.loads(out.stdout)
            answers = [a.get("data", "") for a in j.get("Answer", [])
                       if a.get("type") != 5 or rtype == "CNAME"]
            return j.get("Status", -1), answers
        except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
            continue
    return -1, []


def txt_join(values):
    """TXT из DoH приходит кусками в кавычках ("ab" "cd") — склеиваем."""
    res = []
    for v in values:
        parts = [p for p in v.split('"') if p and p.strip('" ')]
        res.append("".join(parts) if parts else v.strip('"'))
    return res


def redirect_probe(domain: str):
    """Идём по редиректам корня (до 6 хопов): (схема, http-код, финальный URL)."""
    for scheme in ("https", "http"):
        try:
            out = subprocess.run(
                ["curl", "-sIL", "-o", "/dev/null", "--max-time", "20",
                 "--max-redirs", "6", "-w", "%{http_code}\t%{url_effective}",
                 f"{scheme}://{domain}/"],
                capture_output=True, text=True, timeout=30)
            code, url = out.stdout.strip().split("\t", 1)
            if code != "000":
                return scheme, code, url
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
    return None, "000", ""


def check(entry: dict) -> dict:
    domain, hosting = entry["domain"], entry["hosting"]
    target = entry["redirect"]
    exp = EXPECT[hosting]
    r = dict(entry)
    r["issues"] = []
    add = r["issues"].append

    st, ns = doh(domain, "NS")
    r["ns"] = sorted(x.rstrip(".").lower() for x in ns)
    if st == 3:
        add("NXDOMAIN — домен не делегирован/не существует")
        return r
    if st == -1:
        add("DNS недоступен (сеть) — перезапустить проверку")
        return r

    _, mx = doh(domain, "MX")
    mx_hosts = [m.split()[-1].rstrip(".").lower() for m in mx if m.split()]
    r["mx"] = mx_hosts
    if not mx_hosts:
        add(f"нет MX — добавить: MX @ 10 {exp['mx']}.")
    else:
        if not any(exp["mx"] in h for h in mx_hosts):
            add(f"MX {mx_hosts} не {exp['title']} — нужен {exp['mx']}")
        extra = [h for h in mx_hosts if exp["mx"] not in h]
        if extra and any(exp["mx"] in h for h in mx_hosts):
            add(f"лишние MX {extra} — удалить (почта уедет мимо {exp['title']})")

    _, txt_raw = doh(domain, "TXT")
    txts = txt_join(txt_raw)
    spf = [t for t in txts if t.lower().startswith("v=spf1")]
    r["spf"] = spf
    if not spf:
        add(f"нет SPF — добавить: TXT @ \"v=spf1 redirect={exp['spf']}\"")
    else:
        if len(spf) > 1:
            add("НЕСКОЛЬКО SPF-записей (permerror) — оставить одну")
        if not any(exp["spf"] in s for s in spf):
            add(f"SPF без {exp['spf']}: {spf}")
    r["verify_txt"] = [t.strip() for t in txts
                       if "verification" in t.lower() or
                       t.lower().lstrip().startswith(("mailru", "vk", "yandex"))]

    sel = exp["dkim_sel"]
    _, dkim = doh(f"{sel}._domainkey.{domain}", "TXT")
    dkim_v = txt_join(dkim)
    r["dkim"] = any("v=dkim1" in d.lower() and "p=" in d.lower() for d in dkim_v)
    if not r["dkim"]:
        add(f"нет DKIM — включить подпись в панели {exp['title']} и вставить "
            f"TXT {sel}._domainkey")

    _, dmarc = doh(f"_dmarc.{domain}", "TXT")
    dmarc_v = [d for d in txt_join(dmarc) if "v=dmarc1" in d.lower()]
    r["dmarc"] = dmarc_v
    if not dmarc_v:
        add(f"нет DMARC — добавить: TXT _dmarc \"v=DMARC1; p=quarantine; "
            f"rua=mailto:dmarc@{domain}; adkim=s; aspf=s\"")

    _, a = doh(domain, "A")
    r["a"] = a
    scheme, code, url = redirect_probe(domain)
    r["http"] = {"scheme": scheme, "code": code, "final": url}
    if code == "000":
        add(f"редирект корня не настроен ({'нет A-записи, ' if not a else ''}"
            f"сайт не отвечает) — нужен 301 на https://{target}")
    else:
        final_host = url.split("/")[2].lower() if "://" in url else ""
        r["redirect_ok"] = final_host in (target, f"www.{target}")
        if not r["redirect_ok"]:
            add(f"редирект ведёт на {url!r} вместо https://{target}")
        elif not url.startswith("https://"):
            add(f"редирект пришёл в http ({url}) — довести до https")

    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("domains", nargs="*",
                    help="проверить только эти домены (по умолчанию — весь реестр)")
    ap.add_argument("--json", metavar="FILE", help="сохранить полный отчёт в JSON")
    ap.add_argument("--registry", default=REGISTRY, help="путь к domains.json")
    args = ap.parse_args()

    with open(args.registry, encoding="utf-8") as f:
        entries = json.load(f)["domains"]
    if args.domains:
        want = set(args.domains)
        entries = [e for e in entries if e["domain"] in want]
        missing = want - {e["domain"] for e in entries}
        if missing:
            print(f"нет в реестре: {sorted(missing)}", file=sys.stderr)

    results, bad = [], 0
    for e in entries:
        r = check(e)
        results.append(r)
        mark = "OK " if not r["issues"] else "!! "
        print(f"{mark}{r['domain']}  [{EXPECT[r['hosting']]['title']}, "
              f"{r['registrar']}]")
        for iss in r["issues"]:
            print(f"     - {iss}")
        bad += bool(r["issues"])

    print(f"\nитого: {len(results) - bad}/{len(results)} доменов готовы")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print(f"полный отчёт: {args.json}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
