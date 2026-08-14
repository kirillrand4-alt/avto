# -*- coding: utf-8 -*-
r"""Спам-ловушки: адреса, которых на странице не видно человеку.

Владелец 14.08: «могут быть спам-ловушками». Так и есть — это штатный приём
антиспама: адрес прячут от глаз и оставляют парсеру. Письмо на такой ящик
попадает в чёрные списки, и страдает весь домен отправителя, а не одно письмо.

Прячут четырьмя способами, и комментарий — только первый:
  1. <!-- ... --> — блок закомментирован;
  2. style с display:none / visibility:hidden / font-size:0 / opacity:0 /
     height:0 / left:-9999px;
  3. класс-маркер: hidden, honeypot, antispam, sr-only, visually-hidden,
     screen-reader, nodisplay;
  4. скрытое поле формы <input type="hidden" value="адрес">.

Что делаем: НЕ удаляем (ящик может быть жив и единственным), а помечаем и
исключаем из выбора лучшего адреса. Решение об отправке остаётся за письмами,
но по умолчанию такой адрес не должен попадать в рассылку.

    python lovushki_adresov.py [--primenit]
"""
import gzip
import json
import os
import re
import sqlite3
import sys
import time

KESH = os.environ.get('PAGECACHE_DIR', r'C:\seostat\drop\pagecache')
BD = os.environ.get('ENRICH_DB', r'C:\sender\enrich.db')
LOG = r'C:\sender\lovushki_adresov.jsonl'
МЕТКА = 'скрыт от глаз (возможная спам-ловушка): %s'

_КОММ = re.compile(r'<!--.*?-->', re.S)
_СКРЫТ_СТИЛЬ = re.compile(
    r'(?:display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?!\.)'
    r'|font-size\s*:\s*0|height\s*:\s*0|width\s*:\s*0'
    r'|left\s*:\s*-\s*\d{3,}|top\s*:\s*-\s*\d{3,}|text-indent\s*:\s*-\s*\d{3,})', re.I)
_СКРЫТ_КЛАСС = re.compile(
    r'class\s*=\s*"[^"]*(?:hidden|honeypot|honey-pot|antispam|anti-spam|sr-only'
    r'|visually-hidden|screen-reader|nodisplay|no-display|invisible)[^"]*"', re.I)


def _видимость(html, adres):
    """Как адрес лежит на странице: 'виден' или причина, по которой не виден."""
    hl = (html or '').lower()
    a = adres.lower()
    if a not in hl:
        return ''
    # 1) вне комментариев вообще нет — значит только в комментарии
    if a not in _КОММ.sub(' ', hl):
        return 'html-комментарий'
    # 2) ближайший родительский тег со скрывающим стилем или классом.
    #    Смотрим окно НАЗАД от адреса: разметка предка стоит перед ним.
    i = hl.find(a)
    okno = hl[max(0, i - 700):i]
    posl = okno.rfind('<')
    if posl >= 0:
        # ближайшие три открывающих тега перед адресом
        куски = re.findall(r'<[a-z][^>]{0,300}>', okno)[-3:]
        for k in куски:
            if _СКРЫТ_СТИЛЬ.search(k):
                return 'style прячет блок'
            if _СКРЫТ_КЛАСС.search(k):
                return 'класс-невидимка'
            if 'type="hidden"' in k or "type='hidden'" in k:
                return 'скрытое поле формы'
    return 'виден'


def проверить(primenit=False):
    c = sqlite3.connect(BD, timeout=60)
    c.row_factory = sqlite3.Row
    по_инн = {}
    for r in c.execute("select inn, email, coalesce(pometka,'') pometka from emails "
                       "where coalesce(source,'')='own-site'"):
        по_инн.setdefault(str(r['inn']), []).append((r['email'].lower(), r['pometka']))
    итог = {'компаний': 0, 'адресов': 0, 'скрытых': 0, 'по_причинам': {}, 'примеры': []}
    находки = []
    for inn, список in по_инн.items():
        p = os.path.join(KESH, '%s.json.gz' % inn)
        if not os.path.exists(p):
            continue
        try:
            d = json.loads(gzip.open(p, 'rb').read().decode('utf-8', 'replace'))
        except Exception:  # noqa: BLE001
            continue
        страницы = [(pg.get('html') or '') for pg in (d.get('pages') or [])]
        if not страницы:
            continue
        итог['компаний'] += 1
        for адрес, пометка in список:
            итог['адресов'] += 1
            причины = set()
            виден = False
            for h in страницы:
                v = _видимость(h, адрес)
                if v == 'виден':
                    виден = True
                    break
                if v:
                    причины.add(v)
            if виден or not причины:
                continue
            причина = sorted(причины)[0]
            итог['скрытых'] += 1
            итог['по_причинам'][причина] = итог['по_причинам'].get(причина, 0) + 1
            if len(итог['примеры']) < 10:
                итог['примеры'].append({'инн': inn, 'почта': адрес, 'причина': причина})
            if МЕТКА.split(':')[0] not in пометка:
                находки.append((inn, адрес, пометка, причина))
    if primenit and находки:
        with open(LOG, 'a', encoding='utf-8') as f:
            for inn, адрес, пометка, причина in находки:
                f.write(json.dumps({'inn': inn, 'email': адрес, 'bylo': пометка,
                                    'prichina': причина}, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        for inn, адрес, пометка, причина in находки:
            нов = ((пометка + '; ') if пометка else '') + (МЕТКА % причина)
            c.execute('update emails set pometka=?, updated_at=? where inn=? and email=?',
                      (нов[:250], time.strftime('%Y-%m-%dT%H:%M:%S'), inn, адрес))
        c.commit()
        итог['помечено'] = len(находки)
    c.close()
    return итог


if __name__ == '__main__':
    print(json.dumps(проверить('--primenit' in sys.argv), ensure_ascii=False)[:1200])
