# -*- coding: utf-8 -*-
"""Новостные вариации письма-1 (ПРИМЕР типа: письмо ссылается на капекс-повод —
строит/запускает/расширяет). Пишутся в variations-cache как n*.json, попадают в
общий пул. Повод — обобщённый пример (не под реальную новость). Через провайдера."""
import os, sys, json, re
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_provider

D = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(D, 'variations-cache'); os.makedirs(CACHE, exist_ok=True)
S = json.load(open('/tmp/samples.json', encoding='utf-8')); REG = S['regions']

# (оборудование, отрасль, повод-пример, адресат)
NEWS = [
 ("винтовой компрессор","металлообработка","запускаете новый цех / расширяете участок ЧПУ","главному инженеру"),
 ("генератор азота","пищевое производство","вводите новую производственную линию","директору"),
 ("дизельная МКС","строительные работы","начали строительство нового производственного корпуса","в отдел снабжения"),
 ("компрессор + сервис","деревообработка","модернизируете производство","начальнику производства"),
 ("компрессор высокого давления","выдув ПЭТ-тары","расширяете мощности розлива","в отдел закупок"),
 ("генератор кислорода","рыбоводство и аквакультура","запускаете новый комплекс","директору"),
]

RULES = ("Отправитель: ООО «Руспром», prokompressor.ru, менеджер Михаил Лиман, 5580+ проектов, "
 "дилер ведущих брендов + свой Enger. Тема 4-7 слов без КАПС/«!». БЕЗ длинных тире. 1 экран, "
 "живой деловой тон, без опечаток, РОВНО один вопрос. Подпись: имя + «ООО «Руспром» · prokompressor.ru». "
 "Атрибуцию/отписку не писать. БЕЗ незаполненных плейсхолдеров — повод пиши обобщённо и деликатно "
 "(«обратили внимание, что вы …»), без выдуманных конкретных фактов/цифр о клиенте.")

def find_json(raw):
    m = re.search(r'\[.*\]', raw, re.S); return m.group(0) if m else None

def gen(i_item):
    i,(equip,industry,event,role) = i_item
    cf = os.path.join(CACHE, f'n{i:02d}.json')
    if os.path.exists(cf): return
    reg = REG[i % len(REG)]
    prompt = (
        f"Ты сильный B2B-копирайтер. Сгенерируй 6 РАЗНЫХ писем первого касания, где ПОВОД — "
        f"замеченная активность компании: «{event}». Оборудование: «{equip}», сегмент «{industry}», "
        f"адресат преимущественно {role} (варьируй и других ЛПР). Логика: заметили развитие -> "
        f"под новые мощности нужен надёжный воздух/оборудование -> мягко предлагаем помощь/подбор. "
        f"Повод деликатный, без лести и без выдуманных деталей. Варьируй заметно тон и заход.\n"
        f"Реальный пруф (по желанию): в регионе {reg['region']} мы реализовали {reg['projects']} "
        f"проектов, среди них {reg['client']}; всего 5580+.\n\n{RULES}\n\n"
        f'Верни СТРОГО JSON-массив из 6: [{{"role":"","angle":"новостной повод","tone":"","subject":"","body":""}}]')
    for a in range(5):
        try:
            msg = gen_provider._raw_stream([{'role':'user','content':prompt}],'claude-fable-5',3500,thinking=False)
            t = ''.join(b.text for b in msg.content if getattr(b,'type','')=='text')
            arr = json.loads(find_json(t))
            assert isinstance(arr, list) and len(arr) >= 4
            for v in arr:
                v.update({'bucket':f'news{i}','equipment':equip,'industry':industry,
                          'angle':'новостной повод','region':reg['region'],
                          'client':reg['client'],'reg_projects':reg['projects']})
            json.dump(arr, open(cf,'w'), ensure_ascii=False); return
        except Exception as e:
            if a==4: json.dump({'error':str(e)[:100]}, open(cf,'w'), ensure_ascii=False)

if __name__ == '__main__':
    items = list(enumerate(NEWS))
    todo = [it for it in items if not os.path.exists(os.path.join(CACHE, f'n{it[0]:02d}.json'))]
    sys.stderr.write(f'новостных бакетов к генерации: {len(todo)}\n'); sys.stderr.flush()
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(gen, todo))
    sys.stderr.write('новостные готовы\n')
