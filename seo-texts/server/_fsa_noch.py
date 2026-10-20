# -*- coding: utf-8 -*-
# 20.10, ночь; владелец: «со всем согласен, включая Sol для компаний от 1 млрд, про паспорта не забудь». После _fsa_deshevo:
#   A. Sol-агенты (kc_agent_glubokiy, цель Meyer) — компании второй волны от 1 млрд, у которых схема «checko -> ИНН на сайте»
#      сайта не подтвердила (набор fsa1000); по сайтам, что подтвердят агенты, — обход, закупки ЕИС, паспорт.
#   B. Вся база без сайта (уникальные, без активной сделки Meyer, вне волн): Meyer -> fsavm, КЦ -> fsavk. Бесплатно: checko
#      заново (кандидат в сайт), проверка «ИНН на сайте» по кандидатам (декларация / домен почты / checko), без запросов
#      xmlriver. Чужой ИНН на сайте — «сайт группы?» (не выбрасываем, помечаем; в обход не берём). Подтверждённые ->
#      конвейер: обход, доизвлечение, скрытые номера, дообход, контакты закупок ЕИС (kc_zakupki_dobor, от 120 млн), роли
#      (лесенка Meyer / КЦ), аудит, опровергатели, паспорт.
#   C. Контакты закупок ЕИС — и для fsa500p / fsa120s (их конвейеры шли без этого шага).
# Durable: <набор>-sayt-inn.jsonl (fsync, резюм), шаги конвейера — свои jsonl с резюмом, паспорт — site_facts (enrich.db).
import io, json, os, re, shutil, subprocess, sys, threading, time, urllib.parse
from concurrent.futures import ThreadPoolExecutor
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa_noch_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa_noch.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(30)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-700:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import _fsa_deshevo as D  # noqa: E402
import meyer_nalichie as MN  # noqa: E402

_лок = threading.Lock()
ШАГИ = (('kc_kontakty.py', {}), ('kc_doizvlech.py', {}), ('kc_doizvlech_pochty.py', {}), ('kc_skrytye.py', {'KC_SKRYTYE_PROBA': '0'}),
        ('kc_doobhod.py', {}), ('kc_zakupki_dobor.py', {'KC_ZAKUPKI_DOBOR_OT': '120e6', 'KC_ZAKUPKI_POTOKOV': '4'}),
        ('kc_dorazmetka.py', {}), ('kc_audit.py', {}), ('kc_oproverzhenie.py', {}), ('pilot_pasport.py', {}))


def п(*a):
    V.п(*a)


def конвейер(набор, цель, шаги=ШАГИ):
    # 20.10, ревизия: KC_CEL есть в V.ОБЩЕЕ — подменяем внутри (иначе TypeError «multiple values for KC_CEL»)
    env = dict(os.environ, **dict(V.ОБЩЕЕ, KC_CEL=цель), POISK_NABOR=набор, KC_NABOR=набор, PROVIDER_MODEL='gpt-6-luna')
    for файл, доп in шаги:
        питон = V.ПИТОН_ПАНЕЛИ if файл == 'pilot_pasport.py' and os.path.exists(V.ПИТОН_ПАНЕЛИ) else sys.executable
        t0 = time.time()
        pr, лог = V.запуск(файл, dict(env, **доп), набор + '_' + файл[:-3], питон)
        pr.wait()
        п(набор, файл, 'код', pr.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', V.хвост(лог, 300))
    for ф in ('-kontakty.jsonl', '-audit.jsonl', '-oprov.jsonl', '-pasport.jsonl', '-spisok.json'):
        try:
            shutil.copyfile(os.path.join(DIR, набор + ф), os.path.join(ДРОП, набор + ф))
        except Exception as e:  # noqa: BLE001
            п('копия', набор + ф, repr(e)[:80])


def проход_базы(набор, чк):
    сп = json.load(io.open(os.path.join(ДРОП, набор + '-spisok.json'), encoding='utf-8'))['компании']
    вых = os.path.join(DIR, набор + '-sayt-inn.jsonl')
    уже = {i for i, x in V.читать(вых).items() if x.get('сайт') or x.get('как') in ('ИНН ни на одном кандидате', 'кандидатов нет',
                                                                                     'сайт группы? (чужой ИНН)')}
    искл = set(json.load(io.open(os.path.join(ДРОП, 'fsa-isklyuchit.json'), encoding='utf-8')))  # ревизия №2
    очередь = sorted((к for i, к in сп.items() if i not in уже and i not in искл), key=lambda к: -(к.get('выручка') or 0))
    n = [0]

    def одна(к):
        инн = к['inn']
        з = {'inn': инн, 'сайт': '', 'проверено': [], 'запрос': False}
        тел = (чк.get(инн) or {}).get('телефоны') or []
        try:
            # 20.10, ревизия (№6): общая проверка D.проверить — ИНН / телефон checko (вероятный) / чужой ИНН (сайт группы?)
            for сайт, откуда in ((к.get('сайт') or '', 'декларация / домен почты'), ((чк.get(инн) or {}).get('сайт_кандидат') or '', 'checko')):
                if сайт and D.хост(сайт) not in з['проверено']:
                    з['проверено'].append(D.хост(сайт))
                    r = D.проверить(сайт, инн, тел)
                    if r['как'] == 'ИНН':
                        з.update(сайт=D.хост(сайт), как=откуда, страница_с_инн=r['стр'], вероятный=False)
                        break
                    if r['как'] == 'телефон checko' and not з.get('вер'):
                        з['вер'] = (D.хост(сайт), откуда + ' (вероятный: телефон checko на сайте)', r['стр'])
                    if r['чужой_инн'] and not з.get('сайт_группы'):
                        з.update(сайт_группы=D.хост(сайт), чужой_инн=r['чужой_инн'], как_группы=откуда)
            вер = з.pop('вер', None)
            if not з['сайт'] and вер:
                з.update(сайт=вер[0], как=вер[1], страница_с_инн=вер[2], вероятный=True)
            з.setdefault('как', 'сайт группы? (чужой ИНН)' if з.get('сайт_группы') else
                         'ИНН ни на одном кандидате' if з['проверено'] else 'кандидатов нет')
        except Exception as e:  # noqa: BLE001
            з['как'] = 'сбой ' + repr(e)[:100]
        with _лок:
            with io.open(вых, 'a', encoding='utf-8') as f:
                f.write(json.dumps(з, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            n[0] += 1
            if n[0] % 500 == 0:
                п(набор, 'ИНН на сайте: проверено', n[0], 'из', len(очередь))
    with ThreadPoolExecutor(16) as ex:
        list(ex.map(одна, очередь))
    рез = V.читать(вых)
    подтв = {i: x for i, x in рез.items() if x.get('сайт') and i in сп and i not in искл}
    п(набор, 'ИНН на сайте подтверждён', len(подтв), '| сайт группы?', sum(1 for x in рез.values() if x.get('сайт_группы') and not x.get('сайт')),
      '| всего', len(рез))
    shutil.copyfile(вых, os.path.join(ДРОП, набор + '-sayt-inn.jsonl'))
    нов = {i: dict(сп[i], сайт=x['сайт'], сайт_откуда='ИНН на сайте (%s): %s' % (x['как'], x.get('страница_с_инн', '')))
           for i, x in подтв.items()}
    with open(os.path.join(DIR, набор + 'c-spisok.json'), 'w', encoding='utf-8') as f:
        json.dump({'компании': нов, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}, f, ensure_ascii=False)
    return набор + 'c', len(нов)


def ветка_a():
    сп = json.load(io.open(os.path.join(ДРОП, 'fsa120-spisok.json'), encoding='utf-8'))['компании']
    рез = V.читать(os.path.join(DIR, 'fsa120-sayt-inn.jsonl'))
    # 20.10, ревизия: Sol — только тем, кого дешёвая проверка уже прошла и сайта не дала («ИНН ни на одном кандидате» или
    # «сайт группы?»); не дошедшие до проверки (xmlriver кончился, сбой) Sol не получают — их сайт может найтись бесплатно
    итоговые = ('ИНН ни на одном кандидате', 'сайт группы? (чужой ИНН)')
    искл = set(json.load(io.open(os.path.join(ДРОП, 'fsa-isklyuchit.json'), encoding='utf-8')))  # ревизия №2
    нб = {i: к for i, к in сп.items() if (к.get('выручка') or 0) >= 1e9 and i not in искл
          and not (рез.get(i) or {}).get('сайт') and (рез.get(i) or {}).get('как') in итоговые}
    п('A: от 1 млрд без подтверждённого сайта -> Sol-агенты', len(нб))
    if not нб:
        return
    for имя, данные in (('fsa1000-spisok.json', {'компании': нб, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}),
                        ('fsa1000-glubokiy-vhod.json', {i: {'отклонены': ''} for i in нб})):
        with open(os.path.join(ДРОП, имя), 'w', encoding='utf-8') as f:
            json.dump(данные, f, ensure_ascii=False)
    V.агенты('fsa1000')
    V.досбор('fsa1000')
    конвейер('fsa1000p', 'meyer', (('kc_zakupki_dobor.py', {'KC_ZAKUPKI_DOBOR_OT': '120e6', 'KC_ZAKUPKI_POTOKOV': '4'}), ('kc_dorazmetka.py', {})))


def ветка_b():
    наборы = ('fsavm', 'fsavk')
    сп = {}
    for н in наборы:
        сп.update(json.load(io.open(os.path.join(ДРОП, н + '-spisok.json'), encoding='utf-8'))['компании'])
    порядок = sorted(сп, key=lambda i: -(сп[i].get('выручка') or 0))
    with open(os.path.join(ДРОП, 'fsavse-inn.json'), 'w', encoding='utf-8') as f:
        json.dump(порядок, f)
    п('B: checko заново (кандидат в сайт) по базе без сайта', len(порядок))
    pr, лог = V.запуск('fsa_meyer_checko.py', dict(os.environ, CHECKO_VHOD='fsavse-inn.json', CHECKO_ZANOVO='1',
                                                    PYTHONIOENCODING='utf-8'), 'fsavse_checko')
    pr.wait()
    time.sleep(60)
    while V.идёт('fsa_meyer_checko.py'):
        time.sleep(120)
    чк = {}
    for s in io.open(os.path.join(DIR, 'fsa-meyer-checko.jsonl'), encoding='utf-8', errors='replace'):
        try:
            y = json.loads(s)
        except ValueError:
            continue
        if y.get('inn') and y.get('итог') == 'ok':
            чк[y['inn']] = y
    п('B: checko готов, кандидатов в сайт', sum(1 for i in порядок if (чк.get(i) or {}).get('сайт_кандидат')))
    for н, цель in (('fsavm', 'meyer'), ('fsavk', 'kc')):
        нн, k = проход_базы(н, чк)
        if k:
            конвейер(нн, цель)


def main():
    п('жду _fsa_deshevo')
    while V.идёт('_fsa_deshevo.py'):
        time.sleep(180)
    п('_fsa_deshevo закончен')
    for н in ('fsa500p', 'fsa120s'):
        if os.path.exists(os.path.join(DIR, н + '-kontakty.jsonl')):
            конвейер(н, 'meyer', (('kc_zakupki_dobor.py', {'KC_ZAKUPKI_DOBOR_OT': '120e6', 'KC_ZAKUPKI_POTOKOV': '4'}), ('kc_dorazmetka.py', {})))
    тa = threading.Thread(target=ветка_a)
    тa.start()
    ветка_b()
    тa.join()
    п('НОЧЬ: ГОТОВО')


main()
