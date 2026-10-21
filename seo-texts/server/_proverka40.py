# -*- coding: utf-8 -*-
# 21.10, владелец: «Проверь выборку 40 компаний, что это именно их сайты» — сайты, подтверждённые Luna-агентами (fsa120L).
# Независимо от агента: скрипт заново открывает главную и до 4 страниц «контакты / реквизиты / о компании», ищет ИНН и ОГРН,
# затем Sol (провайдер) по тексту страниц решает: «свой» / «группа» / «чужой» / «нельзя понять», с цитатой.
# Выборка — случайные 40 (seed 2110) из подтверждённых. Durable: proverka40.jsonl (fsync). Лог: proverka40_*.log.
import io, json, os, random, re, subprocess, sys, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'proverka40_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_proverka40.py'), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(20)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-500:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import meyer_nalichie as MN  # noqa: E402
import verify_company as VC  # noqa: E402

ВЫХ = os.path.join(DIR, 'proverka40.jsonl')
сп = json.load(io.open(os.path.join(DIR, 'fsa120L-spisok.json'), encoding='utf-8'))['компании']
аг = V.читать(os.path.join(DIR, 'fsa120L-glubokiy.jsonl'))
подтв = sorted(i for i, x in аг.items() if i in сп and ((x.get('сайт_завода') and x.get('сайт_завода_чей')) or
                                                        (x.get('сайт_холдинга') and x.get('холдинг_подтверждён'))))
выб = random.Random(2110).sample(подтв, min(40, len(подтв)))
V.п('подтверждённых', len(подтв), '| выборка', len(выб))
ССЫЛКИ = re.compile(r'контакт|реквизит|о компании|о нас|о предприятии|contact|rekvizit|requisit|about|o-kompanii|kompaniya', re.I)


def текст(html):
    html = re.sub(r'(?is)<(script|style|noscript)[^>]*>.*?</\1>', ' ', html or '')
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def страницы(сайт):
    база = сайт if '//' in сайт else 'https://' + сайт
    ст, html, *_ = MN.скачать(база)
    if not (ст.startswith('ok') and html):
        return [], ст
    out, ссылки = [(база, текст(html))], []
    for href, анкор in re.findall(r'(?is)<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html):
        u = urllib.parse.urljoin(база, href)
        if urllib.parse.urlsplit(u).hostname == urllib.parse.urlsplit(база).hostname and ССЫЛКИ.search(href + ' ' + текст(анкор)) \
                and u not in ссылки:
            ссылки.append(u)
    for u in ссылки[:4]:
        ст2, h2, *_ = MN.скачать(u)
        if ст2.startswith('ok') and h2:
            out.append((u, текст(h2)))
    return out, 'ok'


ПР = '''Проверь, принадлежит ли сайт компании. Компания: «{имя}», ИНН {инн}, регион {рег}.
Сайт: {сайт}. Ниже текст его страниц (главная, контакты, реквизиты, о компании). Скрипт нашёл на страницах: ИНН компании — {есть_инн}; другие ИНН — {чужие}.

{стр}

Ответь строго JSON без пояснений вокруг: {{"вердикт": "свой" | "группа" | "чужой" | "нельзя понять", "почему": "1–2 фразы", "цитата": "дословный фрагмент со страницы, на котором основан вывод"}}
«свой» — сайт этой компании (её ИНН/юрназвание/реквизиты, или название и город/адрес совпадают однозначно).
«группа» — сайт холдинга/бренда/управляющей компании, куда она входит, а не её собственный.
«чужой» — другая компания (однофамилец, дилер, каталог, справочник, площадка).
«нельзя понять» — на страницах нет данных для вывода.'''


def одна(инн):
    x, к = аг[инн], сп[инн]
    сайт = (x.get('сайт_завода') if x.get('сайт_завода_чей') else '') or x.get('сайт_холдинга')
    стр, ст = страницы(сайт)
    весь = ' '.join(т for _, т in стр)
    инны = set(re.findall(r'(?<!\d)(\d{10}|\d{12})(?!\d)', весь))
    есть = инн in инны
    чужие = sorted(i for i in инны if i != инн and re.search(r'ИНН\D{0,15}' + i, весь))[:5]
    з = {'inn': инн, 'имя': к.get('имя'), 'регион': к.get('регион'), 'выручка': к.get('выручка'), 'сайт': сайт,
         'агент_как': x.get('сайт_завода_чей') or ('холдинг: ' + str((x.get('доказательство_холдинга') or {}).get('цитата', ''))[:200]),
         'открылся': ст, 'страниц': len(стр), 'инн_на_сайте': есть, 'чужие_инн': чужие}
    if стр:
        кусок = '\n\n'.join('[%s]\n%s' % (u, т[:2500]) for u, т in стр)[:9000]
        отв = ''
        for _ in range(3):
            try:
                отв = VC._provider_call_stdlib(ПР.format(имя=к.get('имя'), инн=инн, рег=к.get('регион'), сайт=сайт, есть_инн='да' if есть else 'нет',
                                                         чужие=', '.join(чужие) or 'нет', стр=кусок), model='gpt-6-sol') or ''
                if отв:
                    break
            except Exception as e:  # noqa: BLE001
                отв = 'сбой ' + repr(e)[:80]
                time.sleep(20)
        m = re.search(r'\{.*\}', отв or '', re.S)
        try:
            з.update(json.loads(m.group(0)) if m else {'вердикт': 'сбой модели', 'почему': (отв or '')[:200]})
        except ValueError:
            з.update({'вердикт': 'сбой модели', 'почему': (отв or '')[:200]})
    else:
        з.update({'вердикт': 'не открылся', 'почему': ст})
    with io.open(ВЫХ, 'a', encoding='utf-8') as f:
        f.write(json.dumps(з, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    V.п(инн, з.get('вердикт'), сайт, 'ИНН на сайте' if есть else '')
    return з


if os.path.exists(ВЫХ):
    os.remove(ВЫХ)
with ThreadPoolExecutor(10) as ex:
    рр = list(ex.map(одна, выб))
from collections import Counter  # noqa: E402
V.п('ИТОГ', dict(Counter(r.get('вердикт') for r in рр)), '| ИНН на сайте', sum(r['инн_на_сайте'] for r in рр))
import shutil  # noqa: E402
shutil.copyfile(ВЫХ, os.path.join(ДРОП, 'proverka40.jsonl'))
V.п('ГОТОВО')
