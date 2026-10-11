# -*- coding: utf-8 -*-
r"""Группы компаний: один сайт на несколько ИНН списка (владелец 11.10: «да, сделай»; ревизия №45).

Беда: каждый ИНН обходился и проверялся отдельно. Номер завода, найденный на общем сайте холдинга, у соседнего ИНН —
«чужой» и в «Снято», а сам завод его не получает; номер управляющей компании стоит «своим» у 3–5 дочек.

Шаг 0. Группа — хост, общий для ≥2 ИНН списка, у которых связь с сайтом доказана: ИНН на сайте (инн_живой), домен за
       ИНН в базе обзвона или проверка сайта «та же/группа». Тёзки на чужом сайте в группу не входят.
Шаг 1. Пул контактов хоста — номера и почты из обходов всех членов (ключ «номер|доб» / «почта|»).
Шаг 2. Владелец каждого контакта: база обзвона (телефон/почта за одним членом) — сразу; иначе модель по фрагменту
       страницы: член группы | «группа» (общий контакт холдинга/УК) | «площадка» (предприятие группы вне списка, с
       названием) | «чужой» (дилер, магазин, банк, госорган, разработчик).
Выход: <набор>-gruppy.jsonl (fsync, резюм по домену) -> дроп. Excel (pilot_xlsx): свои контакты — в карточку члена,
общие — один раз (у головной) + лист «Группы», площадки — лист «Лиды группы».

    KC_NABOR=<набор> python kc_gruppy.py     (KC_GRUPPY_DOMENY=a.ru,b.ru — только эти; KC_GRUPPY_VYHOD — другой файл)
"""
import io
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

DIR = r'C:\sender\server'
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import kc_kontakty as KK  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

НАБОР = os.environ.get('KC_NABOR', 'pilot')
ВЫХОД = os.path.join(DIR, os.environ.get('KC_GRUPPY_VYHOD') or (НАБОР + '-gruppy.jsonl'))
ТОЛЬКО = {x.strip() for x in os.environ.get('KC_GRUPPY_DOMENY', '').split(',') if x.strip()}
КУСОК = 30
_лок = threading.Lock()

ПРОМПТ = (
    'Сайт {домен} общий для нескольких юрлиц одной группы (холдинга). Юрлица из нашего списка:\n{члены}\n\n'
    'Ниже контакты с этого сайта (номер или e-mail) и фрагмент страницы перед ним.\n{контакты}\n\n'
    'Для КАЖДОГО контакта реши, чей он:\n'
    '— буква юрлица из списка (A, B, …) — контакт относится к нему: его завод, офис, отдел, сотрудник; подпись, '
    'название или город блока указывают на него;\n'
    '— «группа» — общий контакт холдинга или управляющей компании (единая приёмная, общий отдел закупок/снабжения, '
    'горячая линия группы) или по фрагменту нельзя отнести к одному юрлицу из списка;\n'
    '— «площадка» — ПРОИЗВОДСТВЕННОЕ предприятие этой же группы, которого нет в списке (завод, элеватор, комбинат, '
    'ферма, карьер под другим названием): укажи его название и город; торговый дом, представительство, региональный '
    'менеджер по продажам группы — это «группа», не площадка;\n'
    '— «чужой» — не группа: дилер, магазин, партнёр, банк, госорган, разработчик сайта.\n'
    'Подсказка «база обзвона: за X» — в нашей базе этот контакт записан за юрлицом X; база бывает неточна (общий адрес '
    'группы записан за одной дочкой) — решай по фрагменту, подсказка лишь в помощь.\n'
    'Ответ — ТОЛЬКО JSON-массив: [{{"n":номер,"чей":"A|B|…|группа|площадка|чужой","площадка":"название, город — '
    'только для площадки","почему":"до 10 слов"}}]')


def цифры(н):
    ц = re.sub(r'\D', '', н or '')
    return ц[-9:] if ц.startswith('375') else ц[-10:]


def база():
    """Домен -> ИНН базы; телефон (10 цифр)/почта -> ИНН; ИНН -> (адрес, регион)."""
    c = sqlite3.connect(r'file:C:\sender\obzvon-index.db?mode=ro', uri=True, timeout=120)
    дом, тел, почт, адр = {}, {}, {}, {}
    for inn, sites, ph, em, a, рег in c.execute('select inn, coalesce(sites,""), coalesce(phones_base,""), '
                                                'coalesce(emails_base,""), coalesce(address,""), coalesce(region,"") from obzvon'):
        inn = str(inn)
        for x in re.split(r'[\s,;|]+', sites):
            if '.' in x:
                дом.setdefault(MN.домен(x), set()).add(inn)
        for x in ph.split('|'):
            if цифры(x):
                тел.setdefault(цифры(x), set()).add(inn)
        for x in em.split('|'):
            if '@' in x:
                почт.setdefault(x.strip().lower(), set()).add(inn)
        адр[inn] = (a[:140], рег)
    c.close()
    return дом, тел, почт, адр


# 11.10: общие зоны и хостинги — поддомены разных владельцев (dsk.vrn.ru и tehnogaz.vrn.ru, *.narod.ru), не группа
ОБЩИЕ_ЗОНЫ = {'narod.ru', 'tilda.ws', 'com.ru', 'spb.ru', 'msk.ru', 'vrn.ru', 'nnov.ru', 'nsk.ru', 'ekb.ru', 'kazan.ru',
              'samara.ru', 'perm.ru', 'omsk.ru', 'tomsk.ru', 'org.ru', 'net.ru', 'pp.ru', 'ru.com', 'regtorg.ru', 'mya5.ru',
              'orgs.biz', '1c-umi.ru', 'clients.site', 'business.site', '1gb.ru', 's2s.ru', 'wixsite.com', 'ucoz.ru',
              'ucoz.com', 'ucoz.net', 'at.ua', 'nethouse.ru', 'bitrix24site.ru', 'bitrix24.ru', 'tw1.ru', 'okis.ru',
              'pulscen.ru', 'onrender.com', 'narod2.ru', 'jimdo.com', 'jimdofree.com', 'ukit.me', 'taplink.cc', 'taplink.ws',
              'webnode.ru', 'wix.com', 'blogspot.com', 'google.com', 'vk.com', 'tiu.ru', 'all.biz', 'flagma.ru', 'blizko.ru',
              'agroserver.ru', 'beget.tech', 'by.ru', 'h1.ru', 'hut.ru'}


def группы(сп, посл, пров, дом_базы):
    кл = {}
    for i, з in посл.items():
        if i.startswith('САЙТ:') or i not in сп or not з.get('сайт'):
            continue
        кл.setdefault(MN.домен(з['сайт']), []).append(i)
    out = {}
    for д, члены in кл.items():
        if len(члены) < 2 or (ТОЛЬКО and д not in ТОЛЬКО) or д in ОБЩИЕ_ЗОНЫ:
            continue
        док = []
        for i in члены:
            живые = {re.sub(r'\D', '', x) for x in посл[i].get('инн_живой') or []}
            if (re.sub(r'\D', '', i) in живые or i in дом_базы.get(д, ()) or
                    ((пров.get(i) or {}).get('итог') in ('та же', 'группа') and MN.домен((пров.get(i) or {}).get('сайт') or '') == д)):
                док.append(i)
        if len(док) >= 2:
            out[д] = sorted(док, key=lambda i: -(сп[i].get('выручка') or 0))
    return out


def пул(члены, посл, аудит, тел_базы, почт_базы):
    кон = {}
    for i in члены:
        ау = (аудит.get(i) or {}).get('номера') or {}
        for н in посл[i].get('номера') or []:
            ключ = (н.get('номер') or н.get('почта') or '') + '|' + (н.get('доб') or '')
            if ключ == '|':
                continue
            x = кон.setdefault(ключ, {'ключ': ключ, 'номер': н.get('номер') or '', 'доб': н.get('доб') or '',
                                      'почта': н.get('почта') or '', 'контекст': '', 'страница': '', 'роль': '',
                                      'фио': '', 'должность': '', 'нашли': [], 'кто': []})
            if len(н.get('контекст') or '') > len(x['контекст']):
                x['контекст'], x['страница'] = н.get('контекст') or '', (н.get('страницы') or [''])[0]
            for п in ('роль', 'фио', 'должность'):
                x[п] = x[п] or н.get(п) or ''
            x['нашли'].append(i)
            в = ау.get(ключ) or {}
            if в.get('кто') and в['кто'] not in x['кто']:
                x['кто'].append(в['кто'])
    for x in кон.values():
        кандидаты = (тел_базы.get(цифры(x['номер'])) if x['номер'] else почт_базы.get(x['почта'].lower())) or set()
        x['база'] = sorted(set(кандидаты) & set(члены))
    return list(кон.values())


def одна(д, члены, сп, посл, аудит, тел_базы, почт_базы, адр):
    буквы = {chr(65 + k): i for k, i in enumerate(члены[:26])}
    контакты = пул(члены, посл, аудит, тел_базы, почт_базы)
    # 11.10, тест на 6 группах: база обзвона как окончательное решение ошибалась на общих адресах группы
    # (apkkubanhleb@yandex.ru, info@sibglass.ru за одной дочкой) — теперь только подсказка модели
    решено, к_модели = [], list(контакты)
    буква_инн = {i: б for б, i in буквы.items()}
    описание = '\n'.join('%s. ИНН %s — %s; регион %s%s' % (б, i, сп[i]['имя'], сп[i].get('регион') or (адр.get(i) or ('', ''))[1],
                                                             ('; адрес ' + адр[i][0]) if адр.get(i) and адр[i][0] else '')
                         for б, i in буквы.items())
    for k in range(0, len(к_модели), КУСОК):
        кусок = к_модели[k:k + КУСОК]
        список = '\n'.join('%d. %s%s — «…%s…»%s' % (
            j + 1, x['номер'] or x['почта'], (' доб. ' + x['доб']) if x['доб'] else '', x['контекст'][-380:],
            (' [проверка ранее: ' + '; '.join(x['кто'][:2]) + ']') if x['кто'] else '') +
            ((' [база обзвона: за ' + ', '.join(буква_инн[i] for i in x['база'] if i in буква_инн) + ']') if x['база'] else '')
            for j, x in enumerate(кусок))
        r = KK.модель(ПРОМПТ.format(домен=д, члены=описание, контакты=список), True)
        for j, x in enumerate(кусок):
            о = r.get(j + 1) or {}
            ч = str(о.get('чей') or '').strip()
            владелец = буквы.get(ч.upper()) if len(ч) == 1 else (ч if ч in ('группа', 'площадка', 'чужой') else '')
            решено.append(dict(x, владелец=владелец or '', площадка=(о.get('площадка') or '')[:120] if ч == 'площадка' else '',
                               почему=(о.get('почему') or '')[:120] if владелец else 'модель не ответила'))
    for x in решено:
        x.pop('база', None)
    return {'домен': д, 'члены': [{'inn': i, 'имя': сп[i]['имя'], 'выручка': сп[i].get('выручка') or 0} for i in члены],
            'контакты': решено, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}


def записать(з):
    with _лок:
        with io.open(ВЫХОД, 'a', encoding='utf-8') as f:
            f.write(json.dumps(з, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())


def main():
    сп = json.load(io.open(os.path.join(DIR, НАБОР + '-spisok.json'), encoding='utf-8'))['компании']
    посл = {}
    with open(os.path.join(DIR, НАБОР + '-kontakty.jsonl'), 'rb') as f:
        for s in f:
            try:
                з = json.loads(s)
            except ValueError:
                continue
            if з.get('inn'):
                посл[з['inn']] = з
    посл = {i: з for i, з in посл.items() if з.get('итог') == 'ok'}
    аудит, пров = {}, {}
    for ф, куда in (('-audit.jsonl', аудит), ('-sayt-proverka.jsonl', пров)):
        п = os.path.join(DIR, НАБОР + ф)
        if os.path.exists(п):
            for s in io.open(п, encoding='utf-8', errors='replace'):
                try:
                    x = json.loads(s)
                    куда[x['inn']] = x
                except (ValueError, KeyError):
                    pass
    дом_базы, тел_базы, почт_базы, адр = база()
    гр = группы(сп, посл, пров, дом_базы)
    сделано = set()
    if os.path.exists(ВЫХОД):
        for s in io.open(ВЫХОД, encoding='utf-8', errors='replace'):
            try:
                сделано.add(json.loads(s)['домен'])
            except (ValueError, KeyError):
                pass
    задачи = [(д, ч) for д, ч in гр.items() if д not in сделано]
    print('групп', len(гр), 'ИНН в группах', sum(len(ч) for ч in гр.values()), 'к разбору', len(задачи), flush=True)
    n = [0]

    def шаг(x):
        try:
            записать(одна(x[0], x[1], сп, посл, аудит, тел_базы, почт_базы, адр))
        except Exception as e:  # noqa: BLE001
            print('сбой', x[0], repr(e)[:120], flush=True)
        n[0] += 1
        if n[0] % 20 == 0:
            print('группы %d/%d' % (n[0], len(задачи)), flush=True)

    with ThreadPoolExecutor(int(os.environ.get('KC_POTOKOV_SHAGA', '8'))) as ex:
        list(ex.map(шаг, задачи))
    if not ТОЛЬКО:
        shutil.copyfile(ВЫХОД, os.path.join(r'C:\seostat\drop\drop-storage', НАБОР + '-gruppy.jsonl'))
    сч = {}
    for s in io.open(ВЫХОД, encoding='utf-8'):
        for x in json.loads(s)['контакты']:
            к = x['владелец'] if x['владелец'] in ('группа', 'площадка', 'чужой', '') else 'член группы'
            сч[к] = сч.get(к, 0) + 1
    print('===ИТОГ===')
    print('готово', json.dumps(сч, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
