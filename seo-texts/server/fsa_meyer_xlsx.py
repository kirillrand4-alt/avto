import json, collections, re
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE as ILL
чист=lambda r:[ILL.sub(' ',v) if isinstance(v,str) else v for v in r]
D='fsa_in/'
def f(v):
    try: return float(v or 0)
    except ValueError: return 0.0
ots={}
for s in open(D+'fsa-meyer-otsev.jsonl',encoding='utf-8'):
    y=json.loads(s); ots[y['инн']]=y
wb=Workbook(); sv=wb.active; sv.title='Сводка'
H=['ИНН','Изготовитель','Адрес производства','Деклараций','Последняя декларация','Продукция (до 6)','Почты (из декларации)','Мобильные','Городские','Посредник? (контакт у 5+ компаний)','Сайт (по домену почты)','Уже в базе Meyer','В базе обзвона','Выручка (база обзвона)','ОКВЭД','Активная сделка Meyer','Оценка модели','Почему','Классифицировать']
w1=wb.create_sheet('Изготовители'); w2=wb.create_sheet('Отсеяно')
for w in (w1,w2):
    w.append(H)
    for c in w[1]: c.font=Font(bold=True); c.fill=PatternFill('solid',fgColor='DDEBF7')
сч=collections.Counter(); rows=[]
# 18.10: посредники — почта/телефон у 5+ разных изготовителей (оформитель деклараций), в рассылку и обзвон не брать
кп=collections.Counter(); кт=collections.Counter()
for s_ in open(D+'fsa-meyer-izg.jsonl',encoding='utf-8'):
    z_=json.loads(s_)
    for a in set(z_['почты']): кп[a]+=1
    for t in set(z_['телефоны']): кт[re.sub(r'\D','',t)[-10:]]+=1
ПОР=5
БЕСПЛ={'mail.ru','bk.ru','inbox.ru','list.ru','yandex.ru','ya.ru','gmail.com','rambler.ru','yahoo.com','icloud.com','outlook.com','hotmail.com','internet.ru','yandex.com','mail.com','lenta.ru','autorambler.ru','ro.ru','myrambler.ru','km.ru','narod.ru','yandex.by','tut.by'}
моб=lambda t: re.sub(r'\D','',t)[-10:].startswith('9')
for s in open(D+'fsa-meyer-izg.jsonl',encoding='utf-8'):
    z=json.loads(s); y=ots.get(z['инн']) or {}; z['выручка']=f(z['выручка'])
    отв={'da':'да','可能':'возможно','是':'да'}.get(y.get('ответ',''),y.get('ответ',''))
    почты=[a for a in z['почты'] if кп[a]<ПОР]; тел=[t for t in z['телефоны'] if кт[re.sub(r'\D','',t)[-10:]]<ПОР]
    поср=[a for a in z['почты'] if кп[a]>=ПОР]+[t for t in z['телефоны'] if кт[re.sub(r'\D','',t)[-10:]]>=ПОР]
    z['почты'],z['телефоны']=почты,тел
    r=[z['инн'],z['имя'],z['адрес'],z['деклараций'],z['последняя'],' | '.join(z['продукция']),', '.join(почты),', '.join(t for t in тел if моб(t)),', '.join(t for t in тел if not моб(t)),', '.join(поср),', '.join(sorted({a.split('@')[-1] for a in почты if a.split('@')[-1] not in БЕСПЛ})),z['в_базе_meyer'],'да' if z['в_базе_обзвона'] else '',z['выручка'] or None,z['оквэд'],z['сделка_meyer'],отв,y.get('почему',''),'да' if z['классифицировать'] else '']
    rows.append((отв=='нет', z, r))
rows.sort(key=lambda t:(-t[1]['выручка'], -t[1]['деклараций']))
for drop,z,r in rows:
    (w2 if drop else w1).append(чист(r)); сч['отсеяно' if drop else 'в списке']+=1
    if not drop:
        сч['с почтой']+=bool(z['почты']); сч['с телефоном']+=bool(z['телефоны']); сч['сайт по домену почты']+=any(a.split('@')[-1] not in БЕСПЛ for a in z['почты']); сч['с мобильным']+=any(моб(t) for t in z['телефоны']); сч['посредник убран']+=0; сч['уже в базе Meyer']+=bool(z['в_базе_meyer']); сч['активная сделка Meyer']+=bool(z['сделка_meyer'])
        сч['новые (нет в базе Meyer)']+=not z['в_базе_meyer']; сч['новые с почтой']+=(not z['в_базе_meyer']) and bool(z['почты'])
        сч['юрлица']+=len(z['инн'])==10; сч['выручка от 100 млн']+=z['выручка']>=1e8
w3=wb.create_sheet('Цербер'); w3.append(['Номер в реестре','Вид предприятия','Объект','Адрес объекта','Юрлицо','Юр. адрес','ИНН (DaData)','Кандидатов ИНН'])
for c in w3[1]: c.font=Font(bold=True)
inn={}
for s in open(D+'cerber-meyer-inn.jsonl',encoding='utf-8'):
    y=json.loads(s); inn[(y['юрлицо'],y['рег'])]=y
def рег(a):
    m=re.search(r'Российская Федерация, ([^,]+)',a or ''); return (m.group(1) if m else '').replace('обл.','').replace('край','').replace('Респ.','').strip().lower()[:12]
nc=0
for s in open(D+'cerber-meyer.jsonl',encoding='utf-8'):
    x=json.loads(s)
    if not x.get('номер'): continue
    y=inn.get((x['юрлицо'],рег(x.get('юр_адрес') or x.get('адрес')))) or {}
    w3.append(чист([x['номер'],x['вид'],x['объект'],x['адрес'],x['юрлицо'],x['юр_адрес'],y.get('инн',''),y.get('кандидатов','')])); nc+=1; сч['цербер с ИНН']+=bool(y.get('инн'))
sv.append(['ФСА (декларации соответствия, 238 основ продукции Meyer) + Цербер (реестр предприятий ТС). 18.10']); sv['A1'].font=Font(bold=True)
for k in ('в списке','отсеяно','юрлица','выручка от 100 млн','с почтой','с телефоном','с мобильным','сайт по домену почты','уже в базе Meyer','новые (нет в базе Meyer)','новые с почтой','активная сделка Meyer'): sv.append([k,сч[k]])
sv.append(['почт-посредников (у 5+ компаний)',sum(1 for a,v in кп.items() if v>=ПОР)]); sv.append(['телефонов-посредников',sum(1 for a,v in кт.items() if v>=ПОР)])
sv.append(['Цербер: объектов',nc]); sv.append(['Цербер: с найденным ИНН',сч['цербер с ИНН']])
sv.append([]); sv.append(['Отсеяно: ИП с 1–2 декларациями без профильной продукции (правило) и «точно не нужно ни ФТС/рентген, ни компрессор» (модель). Контакты — из карточек деклараций, где заявитель = изготовитель. Сортировка — по выручке, затем по числу деклараций.'])
sv.column_dimensions['A'].width=40
for w in (w1,w2):
    w.freeze_panes='C2'
    for col,wd in zip('ABCDEFGHIJKLMNOPQRS',(13,40,40,10,12,60,30,18,18,30,22,14,8,14,8,14,10,30,8)): w.column_dimensions[col].width=wd
wb.save('FSA-CERBER-MEYER.xlsx'); print(dict(сч), nc)
