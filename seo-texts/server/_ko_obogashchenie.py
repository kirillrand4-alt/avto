# -*- coding: utf-8 -*-
# 21.10, владелец: «посмотри во всех панелях, какие домены относятся к этим ИНН (KO-inn-ne-v-rabote-20261021.csv, 523 ИНН), и по
# этим доменам надо прогнать полное обогащение контактами (без паспорта)». Домены собраны из всех панелей и баз сервера (sender,
# enrich, обзвон, tehlpr, centrifugal, p25, park…, наборы конвейера) — ko-domeny.json; отсеяны справочники/площадки/служебные и
# упоминания в текстах — ko-domeny-itog.json (до 3 на ИНН, сайт из выгрузки — первым).
# 1) Бесплатная проверка «домен — этой компании»: сайт из выгрузки панели — принимаем; иначе ИНН на сайте (_fsa_deshevo.проверить:
#    главная + реквизиты/контакты/политика; справочники и страницы-списки отсеиваются) или ядро названия на главной.
# 2) Подтверждённые домены -> наборы ko1/ko2/ko3 (первый, второй, третий домен компании) -> обход kc_kontakty (15 стр. + люди +
#    обогатитель), доизвлечение номеров и почт, скрытые номера, дообход ×2, контакты закупок ЕИС (без порога выручки — это крупные
#    заказчики), роли по лесенке КЦ, аудит, опровергатели. Паспорт НЕ строим.
# Durable: ko-domeny-proverka.jsonl (fsync, резюм), шаги — свои jsonl с резюмом. Лог: ko_obogashchenie_*.log.
import io, json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'ko_obogashchenie_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_ko_obogashchenie.py'), '--vnutri'], cwd=DIR,
                         creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(40)
    print('===ИТОГ===', open(лог, encoding='utf-8', errors='replace').read()[-600:])
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import _fsa_deshevo as D  # noqa: E402
import _fsa_noch as N  # noqa: E402
import kc_sayty as KS  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

ВЫХ = os.path.join(DIR, 'ko-domeny-proverka.jsonl')
_лок = threading.Lock()
ko = json.load(io.open(os.path.join(ДРОП, 'ko-inn.json'), encoding='utf-8'))
дом = json.load(io.open(os.path.join(ДРОП, 'ko-domeny-itog.json'), encoding='utf-8'))


def проверка(инн, домен):
    инфо = ko[инн]
    if D.хост(инфо.get('сайт') or '') == домен:
        return 'сайт из выгрузки панели'
    r = D.проверить(домен, инн)
    if r['как'] == 'ИНН':
        return 'ИНН на сайте: ' + r['стр']
    ст, html, *_ = MN.скачать('https://' + домен)
    if not (ст.startswith('ok') and html):
        ст, html, *_ = MN.скачать('http://' + домен)
    текст = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).lower().replace('ё', 'е')
    for я in KS.ядра(инфо.get('имя') or ''):
        if я.replace('ё', 'е') in текст:
            return 'название «%s» на главной' % я
    return ''


def main():
    уже = {}
    if os.path.exists(ВЫХ):
        for s in io.open(ВЫХ, encoding='utf-8', errors='replace'):
            try:
                x = json.loads(s)
                уже[(x['inn'], x['домен'])] = x
            except (ValueError, KeyError):
                pass
    пары = [(i, д) for i, дд in дом.items() for д in дд if (i, д) not in уже]
    V.п('КО: пар ИНН–домен к проверке', len(пары), '| уже', len(уже))

    def одна(п):
        i, д = п
        try:
            как = проверка(i, д)
        except Exception as e:  # noqa: BLE001
            как = ''
            V.п('сбой', i, д, repr(e)[:80])
        з = {'inn': i, 'домен': д, 'свой': bool(как), 'как': как}
        with _лок:
            with io.open(ВЫХ, 'a', encoding='utf-8') as f:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            уже[п] = з
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(одна, пары))
    ок = {}
    for i, дд in дом.items():
        ок[i] = [д for д in дд if (уже.get((i, д)) or {}).get('свой')]
    V.п('КО: подтверждено доменов', sum(len(v) for v in ок.values()), '| компаний с доменом', sum(1 for v in ок.values() if v),
        'из', len(ko))
    шаги = tuple(x for x in N.ШАГИ if x[0] != 'pilot_pasport.py')
    шаги = tuple((ф, dict(доп, KC_ZAKUPKI_DOBOR_OT='0') if ф == 'kc_zakupki_dobor.py' else доп) for ф, доп in шаги)
    шаги = шаги[:5] + (('kc_doobhod.py', {'KC_DOOBHOD_SHIROKO': '1'}),) + шаги[5:]
    for k in range(3):
        набор = 'ko%d' % (k + 1)
        сп = {i: {'inn': i, 'имя': ko[i]['имя'], 'регион': ko[i].get('регион') or '—', 'осн': '—', 'все': [], 'сегм': 'КЦ: КО (не в работе)',
                  'выручка': 0.0, 'сайт': вв[k], 'откуда': 'выгрузка КО 21.10; домен из панелей: ' + ((уже.get((i, вв[k])) or {}).get('как') or '')}
              for i, вв in ок.items() if len(вв) > k}
        if not сп:
            continue
        with open(os.path.join(DIR, набор + '-spisok.json'), 'w', encoding='utf-8') as f:
            json.dump({'компании': сп, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}, f, ensure_ascii=False)
        V.п(набор, 'компаний', len(сп))
        N.конвейер(набор, 'kc', шаги)
    V.п('КО: ГОТОВО')


main()
