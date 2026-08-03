# -*- coding: utf-8 -*-
"""Чей это номер: спорные привязки обратного хода судит дешёвая модель провайдера.

ЗАЧЕМ. Мои шаблоны разводят «высокая / средняя / спорная», но спорные так и остаются
нерешёнными: на странице руководства фамилии и телефоны идут вперемешку, и по расстоянию
не разобрать. Формат тут НЕ регулярный — это ровно тот случай, где модель уместна, а
регулярка бессильна. Обратное правило соблюдается: номер по-прежнему добывается регуляркой,
модель только СУДИТ, чей он.

ПОЧЕМУ ДЕШЁВАЯ. Указание владельца 03.08. По прайсу шлюза `gpt-5.6-luna` стоит 0,2 $ за
миллион входных против 5 $ у опуса — в двадцать пять раз дешевле, а задача простая:
прочитать отрывок и сказать, рядом с чьим именем стоит контакт. Отрывок короткий, счёт
идёт на тысячи токенов, не на сотни тысяч.

ЗАСЛОН: модель НЕ ПРИДУМЫВАЕТ. Ей нельзя ответить «да» — только выбрать одно из имён,
которые ей даны, либо сказать «не видно». Ответ, где имя не из списка, отбрасывается.
"""
import json, os, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, '/home/user/avto/seo-texts')
import gen_provider as G

MODEL = os.environ.get('SUD_MODEL', 'gpt-5.6-luna')
VHOD = 'lpr-obratnyy.jsonl'
POTOK = 'sud-chey-nomer.jsonl'

PROMPT = """Ниже отрывок со страницы сайта или из документа. В нём есть контакт и рядом
несколько людей. Скажи, ЧЕЙ это контакт.

ПРАВИЛА:
1. Ответь именем ТОЛЬКО из списка ниже, слово в слово. Никаких других имён.
2. Если по отрывку понять нельзя — ответь «не видно». Это нормальный ответ, гадать нельзя.
3. Смотри на порядок слов: в русских текстах контакт обычно стоит ПОСЛЕ имени и должности
   того, кому принадлежит, но бывает и до — решай по смыслу фразы, а не по расстоянию.

КОНТАКТ: {kontakt}
ИМЕНА НА ВЫБОР: {imena}
ОТРЫВОК: {otryvok}

Ответ строго JSON: {{"chey": "<имя из списка или 'не видно'>", "pochemu": "<до 15 слов>"}}"""


def sobrat(vse=False):
    """Спорные — или ВСЕ найденные контакты.

    Проверять только спорные оказалось мало: на выборке из 128 спорных модель забраковала
    20, то есть каждый шестой. Значит и среди тех, что мои шаблоны сочли «высокой»
    уверенностью, ошибки есть — их просто никто не искал. Судим всё, благо дёшево:
    `gpt-5.6-luna` 0,2 $ за миллион входных против 5 $ у опуса.
    """
    zad = []
    for ln in open(VHOD, encoding='utf-8'):
        if not ln.strip():
            continue
        z = json.loads(ln)
        for k in z.get('kontakty') or []:
            if not vse and k.get('uverennost') != 'спорная':
                continue
            imena = [z['fio']]
            if k.get('chuzhaya_familiya'):
                imena.append(k['chuzhaya_familiya'])
            zad.append({'inn': z['inn'], 'nash': z['fio'], 'dolzhnost': z.get('dolzhnost', ''),
                        'kontakt': k['znachenie'], 'tip': k['tip'],
                        'byla_uverennost': k.get('uverennost', ''),
                        'imena': imena, 'citata': k['citata'],
                        'ssylka': k.get('ssylka', '')})
    return zad


def main():
    zad = sobrat(vse='--vse' in sys.argv)
    gotovo = set()
    if os.path.exists(POTOK):
        for ln in open(POTOK, encoding='utf-8'):
            try:
                z = json.loads(ln)
                gotovo.add((z['inn'], z['nash'], z['kontakt']))
            except Exception:  # noqa: BLE001
                pass
    zad = [z for z in zad if (z['inn'], z['nash'], z['kontakt']) not in gotovo]
    print(f'спорных привязок к суду: {len(zad)} (уже судимых {len(gotovo)}), модель {MODEL}',
          file=sys.stderr, flush=True)
    if not zad or '--zamer' in sys.argv:
        for z in zad[:5]:
            print('  ', z['kontakt'], '|', z['imena'], file=sys.stderr)
        return
    client = G.make_client()
    f = open(POTOK, 'a', encoding='utf-8')
    lock = threading.Lock()
    sch = {'n': 0, 'nash': 0, 'chuzhoy': 0, 'ne_vidno': 0, 'brak': 0, 'err': 0}

    def odin(z):
        p = PROMPT.format(kontakt=z['kontakt'], imena=' | '.join(z['imena']),
                          otryvok=z['citata'][:600])
        try:
            o = G.call(client, [{'role': 'user', 'content': p}], model=MODEL, attempts=3)
            t = ''.join(b.text for b in o.content if b.type == 'text')
            m = re.search(r'\{.*\}', t, re.S)
            d = json.loads(m.group(0)) if m else None
        except Exception as e:  # noqa: BLE001
            return {**z, 'sud': '', 'pochemu': f'сбой: {type(e).__name__}'}
        if not isinstance(d, dict):
            return {**z, 'sud': '', 'pochemu': 'ответ не той формы'}
        chey = (d.get('chey') or '').strip()
        # Имя не из списка — брак: модель придумала. Такое не принимаем.
        if chey and chey.lower() != 'не видно' and chey not in z['imena']:
            return {**z, 'sud': '', 'pochemu': f'БРАК: имя не из списка ({chey[:40]})'}
        return {**z, 'sud': chey, 'pochemu': (d.get('pochemu') or '')[:120]}

    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(odin, zad):
            with lock:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                sch['n'] += 1
                s = r['sud']
                if not s:
                    sch['brak' if 'БРАК' in r['pochemu'] else 'err'] += 1
                elif s.lower() == 'не видно':
                    sch['ne_vidno'] += 1
                elif s == r['nash']:
                    sch['nash'] += 1
                else:
                    sch['chuzhoy'] += 1
                if sch['n'] % 25 == 0:
                    f.flush()
                    print(f"  {sch['n']}/{len(zad)}: наш {sch['nash']}, чужой {sch['chuzhoy']}, "
                          f"не видно {sch['ne_vidno']}, брак {sch['brak']}, сбоев {sch['err']}",
                          file=sys.stderr, flush=True)
    f.close()
    print(f"суд окончен: {sch} → {POTOK}", file=sys.stderr)


if __name__ == '__main__':
    main()
