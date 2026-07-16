# -*- coding: utf-8 -*-
"""Пост-фикс: обернуть первое упоминание клиента ссылкой на страницу его проекта
(если ссылки на этот проект в тексте ещё нет). Работает только по текстовым узлам,
не лезет внутрь существующих <a> и внутрь тегов (alt=...). Идемпотентно.
Запуск: python3 link_projects.py [--dry]"""
import json, glob, os, re, sys

DIR = os.path.dirname(os.path.abspath(__file__))
DRY = '--dry' in sys.argv


def candidates(client):
    """Варианты написания клиента: полное и без ООО/ИП/кавычек."""
    out = []
    c = (client or '').strip()
    if len(c) >= 5:
        out.append(c)
    short = re.sub(r'^(ООО|ИП|АО|ЗАО|ПАО)\s+', '', c).strip('"«» ')
    if len(short) >= 5 and short != c:
        out.append(f'"{short}"')      # в кавычках (частый вид в прозе)
        out.append(f'«{short}»')
        out.append(short)
    return out


def wrap_first(html, needle, url):
    """Обернуть первое вхождение needle ссылкой, только в текстовых узлах вне <a>."""
    chunks = re.split(r'(<a\b.*?</a>)', html, flags=re.S)   # чётные - вне ссылок
    for ci in range(0, len(chunks), 2):
        parts = re.split(r'(<[^>]+>)', chunks[ci])          # чётные - текстовые узлы
        for pi in range(0, len(parts), 2):
            idx = parts[pi].find(needle)
            if idx >= 0:
                parts[pi] = (parts[pi][:idx] + f'<a href="{url}">{needle}</a>'
                             + parts[pi][idx + len(needle):])
                chunks[ci] = ''.join(parts)
                return ''.join(chunks), True
    return html, False


def main():
    pages = wrapped = 0
    rep = []
    for f in sorted(glob.glob(os.path.join(DIR, 'gen', 'payload-*.json'))):
        p = json.load(open(f))
        projs = p.get('projects') or []
        if not projs:
            continue
        rf = f.replace('payload-', 'result-')
        try:
            d = json.load(open(rf))
        except Exception:
            continue
        h = d['text_html']
        changed = False
        for pr in projs:
            url = pr.get('url')
            if not url or f'href="{url}"' in h.replace(f'href="{url}" style="float:right', ''):
                # уже есть в тексте (ссылка карточки не считается - у неё style float:right)
                pass
            body_wo_card = h.replace(f'href="{url}" style="float:right', 'href-card')
            if f'href="{url}"' in body_wo_card:
                continue                       # интекст-ссылка уже стоит
            for cand in candidates(pr.get('client')):
                h2, ok = wrap_first(h, cand, url)
                if ok:
                    h = h2; changed = True; wrapped += 1
                    rep.append(f'- `{p["slug"]}`: «{cand[:40]}» -> {url}')
                    break
        if changed:
            pages += 1
            if not DRY:
                d['text_html'] = h
                json.dump(d, open(rf, 'w'), ensure_ascii=False, indent=1)
    open(os.path.join(DIR, 'link-projects-report.md'), 'w', encoding='utf-8').write(
        f'# Интекст-ссылки на проекты ({"DRY" if DRY else "APPLIED"})\n\n' + '\n'.join(rep))
    print(f'{"[DRY] " if DRY else ""}страниц изменено: {pages} | ссылок добавлено: {wrapped}')


if __name__ == '__main__':
    main()
