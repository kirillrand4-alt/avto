# -*- coding: utf-8 -*-
"""ЕИС: проверка гипотезы «технический контакт лежит в свободном тексте карточки».

Гипотеза взялась не из головы. На Tender.pro обе сессии записали «технических людей не даёт»,
потому что смотрели структурное поле «куратор закупки» — там снабженец. Технарь оказался в
свободном комментарии той же карточки, с прямым мобильным, и прогон по площадке дал
**359 уникальных технических людей с проверенным телефоном в 66 компаниях**. Если в ЕИС тот же
разрыв между полем и свободным текстом, корпус на порядок больше.

Что уже замерено (30.07.2026):
- `zakupki.gov.ru` **из песочницы не отвечает** (curl отдаёт код 000), работаем через раннер;
- фильтр поиска жив: «компрессор» даёт 10 закупок на странице и 11 вхождений слова в ответе,
  контрольная бессмыслица «кастрюлякастрюля» — **ноль** закупок;
- в карточке 223-ФЗ есть блок «Контактная информация» (контактное лицо, почта, телефон) и
  отдельный блок **«Дополнительная информация»** — в первой же открытой карточке он пуст («-»),
  и именно его наполненность надо измерить, а не предположить.

Почему `fetch_url` пачками, а не `eval_js` в браузере: внутристраничный `fetch` на раннере
вернул «Failed to fetch» по всем сорока карточкам. По правилу В8 это считается неисправностью
инструмента, а не свойством источника, но отлаживать браузер дороже, чем взять заведомо
рабочий путь. Пачки стали возможны после починки уникальности id задания.

**Обязательный параметр `name`.** Без него `fetch_url` кладёт ответ на дроп под именем из
последнего сегмента URL, и шесть параллельных запросов к `common-info.html` затирают друг
друга — та же коллизия, что была у id заданий.

Использование:
    python3 eis_probe.py --ids <файл со списком регномеров> [--pachka 6] [--limit 60]
"""
import json
import os
import re
import subprocess
import sys

BAZA = os.path.dirname(os.path.abspath(__file__))
KLIENT = os.path.join(BAZA, 'server', 'run_on_server.py')
DROP = os.path.join(BAZA, 'server', 'drop_client.sh')
RAB = os.path.join('/tmp/claude-0/-home-user-avto/'
                   '520847fd-7699-5483-869b-cf6d49851f67/scratchpad', 'eis')
CARD = ('https://zakupki.gov.ru/223/purchase/public/purchase/info/'
        'common-info.html?regNumber=%s')

TEH = re.compile(r'тех\w*\s+(?:вопрос|характер)|техническ|главн\w+\s+(?:инженер|механик|'
                 r'энергетик)|гл\.?\s*(?:инженер|механик|энергетик)|начальник\s+'
                 r'(?:цеха|компрессорн|управлен|отдела\s+глав)|механик|энергетик|ОГМ|ОГЭ|КИПиА',
                 re.I)
TEL = re.compile(r'(?:\+7|\b8|\b7)[\s(\-]*\d{3,5}[\s)\-]*\d{2,3}[\s\-]*\d{2}[\s\-]*\d{2}\b')


def bez_tegov(h):
    h = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', h)
    return re.sub(r'[ \t]+', ' ', re.sub(r'<[^>]+>', '\n', h))


def kusok(t, posle, dlina):
    i = t.find(posle)
    return re.sub(r'\n+', ' | ', t[i:i + dlina]).strip() if i >= 0 else ''


def vzyat_pachku(ids):
    zad = [{'task': 'fetch_url',
            'args': {'url': CARD % i, 'insecure': True, 'name': f'eis_c_{i}.html'}}
           for i in ids]
    p = subprocess.run([sys.executable, KLIENT, '--many', json.dumps(zad, ensure_ascii=False),
                        '--threads', str(len(zad))], capture_output=True, text=True, timeout=1800)
    m = re.search(r'\[.*\]', p.stdout, re.S)
    return json.loads(m.group(0)) if m else []


def skachat(imya, kuda):
    subprocess.run(['bash', DROP, 'down', imya], cwd=kuda, capture_output=True, timeout=300)
    p = os.path.join(kuda, imya)
    return open(p, encoding='utf-8', errors='replace').read() if os.path.exists(p) else ''


def main():
    ids_file = sys.argv[sys.argv.index('--ids') + 1]
    pachka = int(sys.argv[sys.argv.index('--pachka') + 1]) if '--pachka' in sys.argv else 6
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else 60
    ids = [x.strip() for x in open(ids_file) if x.strip()][:limit]
    os.makedirs(RAB, exist_ok=True)
    print(f'карточек: {len(ids)}, пачками по {pachka}', file=sys.stderr)

    itog = []
    for i in range(0, len(ids), pachka):
        gr = ids[i:i + pachka]
        res = vzyat_pachku(gr)
        for r in res:
            d = (r or {}).get('data') or {}
            imya = d.get('drop_name')
            if not imya:
                itog.append({'id': '?', 'oshibka': str(d.get('error'))[:80]})
                continue
            h = skachat(imya, RAB)
            t = bez_tegov(h)
            rn = re.search(r'eis_c_(\d+)\.html', imya)
            itog.append({
                'id': rn.group(1) if rn else '',
                'bytes': len(h),
                'zakazchik': kusok(t, 'Наименование заказчика', 200),
                'predmet': kusok(t, 'Предмет договора', 200) or kusok(t, 'Наименование закупки', 200),
                'kontakt': kusok(t, 'Контактная информация', 300),
                'dop': kusok(t, 'Дополнительная информация', 400),
                'teh_v_dop': bool(TEH.search(kusok(t, 'Дополнительная информация', 400))),
                'tel_v_dop': TEL.findall(kusok(t, 'Дополнительная информация', 400)),
                'teh_gde_ugodno': bool(TEH.search(t)),
            })
        print(f'  {min(i + pachka, len(ids))}/{len(ids)}', file=sys.stderr, flush=True)

    out = os.path.join(BAZA, 'engineers-lens', 'centro', 'eis', 'eis-probe.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(itog, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    got = [x for x in itog if x.get('bytes')]
    dop_ne_pusto = [x for x in got if len(re.sub(r'Дополнительная информация|[\s|\-]', '',
                                                 x.get('dop') or '')) > 3]
    print(f'\nЗАМЕР, знаменатель {len(got)} открытых карточек из {len(itog)} запрошенных:')
    print(f'  «Дополнительная информация» непуста: {len(dop_ne_pusto)}')
    print(f'  техническое слово в «Дополнительной»: {sum(1 for x in got if x["teh_v_dop"])}')
    print(f'  телефон в «Дополнительной»: {sum(1 for x in got if x["tel_v_dop"])}')
    print(f'  техническое слово где угодно в карточке: {sum(1 for x in got if x["teh_gde_ugodno"])}')
    print(f'→ {out}')


if __name__ == '__main__':
    main()
