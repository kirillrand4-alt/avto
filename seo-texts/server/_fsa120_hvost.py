# -*- coding: utf-8 -*-
# 21.10, владелец: «пополнил хмлривер» — хвост второй волны: компании fsa120, которым ночью не хватило xmlriver («xmlriver
# кончился», «поиск не ответил», сбой), — та же проверка «ИНН на сайте» (_fsa_deshevo.одна, от большей выручки к меньшей),
# подтверждённые -> свой набор fsa120t и тот же конвейер, что у fsa120s (обход, доизвлечение, скрытые номера, дообход,
# закупки ЕИС, роли, аудит, опровергатели, паспорт). Durable: fsa120-sayt-inn.jsonl (дописывается), fsa120t-*.jsonl.
import io, json, os, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
DIR = r'C:\sender\server'
ДРОП = r'C:\seostat\drop\drop-storage'
if '--vnutri' not in sys.argv:
    лог = os.path.join(DIR, 'fsa120_hvost_%s.log' % time.strftime('%d%m-%H%M'))
    with open(лог, 'wb') as в:
        p = subprocess.Popen([sys.executable, '-u', os.path.join(DIR, '_fsa120_hvost.py'), '--vnutri'], cwd=DIR,
                             creationflags=0x08 | 0x200, stdin=subprocess.DEVNULL, stdout=в, stderr=subprocess.STDOUT, close_fds=False)
    time.sleep(60)
    print('===ИТОГ===')
    print(json.dumps({'pid': p.pid, 'лог': os.path.basename(лог), 'хвост': open(лог, encoding='utf-8', errors='replace').read()[-700:]},
                     ensure_ascii=False))
    sys.exit(0)
sys.path.insert(0, DIR)
sys.path.insert(0, r'C:\sender')
os.chdir(DIR)
import _fsa_volny as V  # noqa: E402
import _fsa_deshevo as D  # noqa: E402

ШАГИ = (('kc_kontakty.py', {}), ('kc_doizvlech.py', {}), ('kc_doizvlech_pochty.py', {}), ('kc_skrytye.py', {'KC_SKRYTYE_PROBA': '0'}),
        ('kc_doobhod.py', {}), ('kc_zakupki_dobor.py', {'KC_ZAKUPKI_DOBOR_OT': '120e6', 'KC_ZAKUPKI_POTOKOV': '4'}),
        ('kc_dorazmetka.py', {}), ('kc_audit.py', {}), ('kc_oproverzhenie.py', {}), ('pilot_pasport.py', {}))


def main():
    сп = json.load(io.open(os.path.join(ДРОП, 'fsa120-spisok.json'), encoding='utf-8'))['компании']
    искл = set(json.load(io.open(os.path.join(ДРОП, 'fsa-isklyuchit.json'), encoding='utf-8')))
    было = V.читать(D.ВЫХ)
    хвост = [к for i, к in сп.items() if i not in искл and i in было and not было[i].get('сайт')
             and (было[i].get('как') in ('xmlriver кончился', 'поиск не ответил') or str(было[i].get('как', '')).startswith('сбой'))]
    хвост.sort(key=lambda к: -(к.get('выручка') or 0))
    V.п('хвост fsa120 к проверке', len(хвост))
    чк = {}
    for s in io.open(os.path.join(DIR, 'fsa-meyer-checko.jsonl'), encoding='utf-8', errors='replace'):
        try:
            y = json.loads(s)
        except ValueError:
            continue
        if y.get('inn') and y.get('итог') == 'ok':
            чк[y['inn']] = y
    n = [0]
    лок = threading.Lock()

    def шаг(к):
        try:
            D.одна(к, чк)
        except Exception as e:  # noqa: BLE001
            D.записать({'inn': к['inn'], 'сайт': '', 'как': 'сбой ' + repr(e)[:100]})
        with лок:
            n[0] += 1
            if n[0] % 100 == 0:
                V.п('проверено', n[0], 'из', len(хвост))
    with ThreadPoolExecutor(12) as ex:
        list(ex.map(шаг, хвост))
    рез = V.читать(D.ВЫХ)
    нов = {к['inn']: dict(к, сайт=рез[к['inn']]['сайт'], сайт_откуда='ИНН на сайте (%s): %s' % (
        рез[к['inn']].get('как', ''), рез[к['inn']].get('страница_с_инн', '')))
        for к in хвост if (рез.get(к['inn']) or {}).get('сайт')}
    V.п('хвост: сайт подтверждён', len(нов), 'из', len(хвост), '| ещё без запроса',
        sum(1 for к in хвост if (рез.get(к['inn']) or {}).get('как') == 'xmlriver кончился'))
    if not нов:
        return
    набор = 'fsa120t'
    with open(os.path.join(DIR, набор + '-spisok.json'), 'w', encoding='utf-8') as f:
        json.dump({'компании': нов, 'снято': {}, 'ниже_порога': {}, 'на_решение': {}}, f, ensure_ascii=False)
    # шаги конвейера fsa120s ещё могут идти — ждём, чтобы не делить модель/ЕИС на два набора сразу
    while V.идёт('_fsa_deshevo.py'):
        time.sleep(120)
    env = dict(os.environ, **dict(V.ОБЩЕЕ, KC_CEL='meyer'), POISK_NABOR=набор, KC_NABOR=набор, PROVIDER_MODEL='gpt-6-luna')
    for файл, доп in ШАГИ:
        питон = V.ПИТОН_ПАНЕЛИ if файл == 'pilot_pasport.py' and os.path.exists(V.ПИТОН_ПАНЕЛИ) else sys.executable
        t0 = time.time()
        pr, лог = V.запуск(файл, dict(env, **доп), набор + '_' + файл[:-3], питон)
        pr.wait()
        V.п(набор, файл, 'код', pr.returncode, 'за %.1f мин' % ((time.time() - t0) / 60), '|', V.хвост(лог, 300))
    V.п('ХВОСТ fsa120: ГОТОВО')


main()
