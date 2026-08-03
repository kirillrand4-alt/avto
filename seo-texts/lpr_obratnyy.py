# -*- coding: utf-8 -*-
"""Обратный ход в песочнице: по найденному человеку добираем ЕГО контакт.

ЗАЧЕМ ЗДЕСЬ, А НЕ НА СЕРВЕРЕ. Серверный `lpr_serp back` берёт людей из таблицы `people`
панели, где `source LIKE 'поиск-ЛПР%'`. Мой поиск по должности пишет в песочницу, в панель
не пишет — значит серверный обратный ход про этих людей просто не знает и через пару
заданий упрётся в пустоту. Замер сервера: 51 человек за 417 с, 14 телефонов и 11 почт.

Здесь тот же запрос — «"Фамилия Имя Отчество" "<компания>"» — но по СВОЕМУ потоку и в
восемь потоков. Ищем страницу самого человека: профиль на отраслевом портале, программа
конференции с почтой, карточка спикера, интервью в заводской газете.

ЗАСЛОН ОТ ЧУЖОГО НОМЕРА. Номер берётся, только если в том же отрывке стоит фамилия
человека. Страница, где фамилия есть, а номер относится к приёмной соседнего абзаца, даёт
телефон не тому — на этом уже терялись контакты. Поэтому: сначала ищем фамилию, потом
номер в окне вокруг неё, и записываем расстояние между ними, чтобы человек мог судить сам.
"""
import json, os, re, sys, threading, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

for _l in open('/home/user/work/.keys-3s.env'):
    if '=' in _l:
        _k, _v = _l.strip().split('=', 1)
        os.environ.setdefault(_k, _v)
USER, KEY = os.environ['XMLRIVER_USER'], os.environ['XMLRIVER_KEY']

VHOD = 'lpr-pesochnica.jsonl'
POTOK = 'lpr-obratnyy.jsonl'
DOC = re.compile(r'<doc>(.*?)</doc>', re.S)
URL = re.compile(r'<url>([^<]*)</url>')
ZAG = re.compile(r'<title>(.*?)</title>', re.S)
PASS = re.compile(r'<passage>(.*?)</passage>', re.S)
OSH = re.compile(r'<error[^>]*>([^<]*)')
PEREZAPROS = re.compile(r'перезапрос|повторите|не получен|timeout|таймаут', re.I)
# Телефон: код страны и десять цифр. Однозначная запись, спутать не с чем.
TEL = re.compile(r'(?:\+7|\b8)[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')
POCHTA = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
# Реквизит рядом с числом — не телефон. Тот же заслон, что в сборщике Тендер.Про.
NE_TEL = re.compile(r'(?:ИНН|ОГРН|КПП|р/с|к/с|БИК|лот|№)\D{0,4}$', re.I)
MUSOR = re.compile(r'(avito|youla|hh\.ru|superjob|rabota|zoon|yell|orgpage|list-org|'
                   r'rusprofile|checko|sbis|vk\.com/away)', re.I)


def _bez(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s or '')).strip()


def serp(q, popytok=5):
    url = (f'https://xmlriver.com/search/xml?user={USER}&key={KEY}'
           f'&query={urllib.parse.quote(q)}')
    for p in range(popytok):
        try:
            b = urllib.request.urlopen(
                urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}),
                timeout=60).read().decode('utf-8', 'replace')
        except Exception as e:  # noqa: BLE001
            if p == popytok - 1:
                return [], f'{type(e).__name__}: {str(e)[:60]}'
            time.sleep(2 * (p + 1))
            continue
        m = OSH.search(b)
        if m:
            t = _bez(m.group(1))
            if PEREZAPROS.search(t) and p < popytok - 1:
                time.sleep(3 * (p + 1))
                continue
            return [], f'xmlriver: {t[:80]}'
        out = []
        for d in DOC.findall(b):
            u = URL.search(d)
            z = ZAG.search(d)
            out.append({'url': u.group(1) if u else '',
                        'tekst': _bez(z.group(1) if z else '') + ' ' +
                                 ' '.join(_bez(x) for x in PASS.findall(d))})
        return out, ''
    return [], 'не дошло'


def kontakty_ryadom(tekst, fio):
    """Контакты, стоящие РЯДОМ с фамилией. Расстояние пишется в запись."""
    fam = fio.split()[0]
    if len(fam) < 4:
        return []
    poz = [m.start() for m in re.finditer(re.escape(fam), tekst)]
    if not poz:
        return []
    out = []
    for rx, tip in ((TEL, 'телефон'), (POCHTA, 'почта')):
        for m in rx.finditer(tekst):
            if tip == 'телефон' and NE_TEL.search(tekst[max(0, m.start() - 12):m.start()]):
                continue
            d = min(abs(m.start() - p) for p in poz)
            if d <= 400:
                out.append({'znachenie': m.group(0).strip(), 'tip': tip,
                            'znakov_do_familii': d,
                            'citata': tekst[max(0, m.start() - 120):m.start() + 80]})
    return out


def main():
    lim = int(sys.argv[sys.argv.index('--lim') + 1]) if '--lim' in sys.argv else 10 ** 9
    pot = int(sys.argv[sys.argv.index('--potokov') + 1]) if '--potokov' in sys.argv else 8
    lyudi = {}
    for ln in open(VHOD, encoding='utf-8'):
        if not ln.strip():
            continue
        z = json.loads(ln)
        for ch in z.get('lyudi') or []:
            # Инициалы вместо имени запросу не помогают: «Иванов И.И.» находит однофамильцев
            # по всей стране. Берём только полные ФИО.
            if ch.get('vid_imeni') != 'полное ФИО':
                continue
            k = (z['inn'], ch['fio'])
            if k not in lyudi:
                lyudi[k] = {'inn': z['inn'], 'predpriyatie': z['predpriyatie'],
                            'fio': ch['fio'], 'dolzhnost': ch['dolzhnost']}
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
                gotovo.add((z['inn'], z['fio']))
            except Exception:  # noqa: BLE001
                pass
    zad = [v for k, v in lyudi.items() if k not in gotovo][:lim]
    print(f'людей с полным ФИО {len(lyudi)}, уже спрошено {len(gotovo)}, '
          f'к обходу {len(zad)}, потоков {pot}', file=sys.stderr, flush=True)

    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'n': 0, 'sboev': 0, 's_tel': 0, 'tel': 0, 'pocht': 0}

    def odin(c):
        imya = re.sub(r'^(ООО|АО|ПАО|ЗАО|ОАО|НАО|ГУП|МУП|ФГУП)\s+', '', c['predpriyatie'])
        imya = re.sub(r'["«»]', '', imya).strip()
        q = f'"{c["fio"]}" "{imya}"'
        docs, err = serp(q)
        naydeno = []
        for d in docs:
            if MUSOR.search(d['url']):
                continue
            for k in kontakty_ryadom(d['tekst'], c['fio']):
                naydeno.append({**k, 'ssylka': d['url']})
        return {**c, 'zapros': q, 'err': err, 'stranic': len(docs), 'kontakty': naydeno}

    with ThreadPoolExecutor(max_workers=pot) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                sch['n'] += 1
                sch['sboev'] += 1 if r['err'] else 0
                t = sum(1 for k in r['kontakty'] if k['tip'] == 'телефон')
                p = sum(1 for k in r['kontakty'] if k['tip'] == 'почта')
                sch['tel'] += t
                sch['pocht'] += p
                sch['s_tel'] += 1 if t else 0
                if sch['n'] % 50 == 0:
                    f.flush()
                    os.fsync(f.fileno())
                    print(f"  {sch['n']}/{len(zad)} человек, с телефоном {sch['s_tel']}, "
                          f"телефонов {sch['tel']}, почт {sch['pocht']}, "
                          f"сбоев {sch['sboev']}", file=sys.stderr, flush=True)
    f.flush()
    f.close()
    print(f"готово: людей {sch['n']}, У СКОЛЬКИХ НАШЁЛСЯ ТЕЛЕФОН {sch['s_tel']}, "
          f"телефонов {sch['tel']}, почт {sch['pocht']}, СБОЕВ {sch['sboev']} "
          f"(сбой это не ноль) → {POTOK}", file=sys.stderr)


if __name__ == '__main__':
    main()
