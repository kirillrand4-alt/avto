import openpyxl, collections, json, re
D="/root/.claude/uploads/eb90afa2-9dfc-57d7-acb9-abafd7969908/"
S="/tmp/claude-0/-home-user-avto/eb90afa2-9dfc-57d7-acb9-abafd7969908/scratchpad/fsa/"
out={}
for f,tag in [('33cfef56-FSA-MEYER-v4-KC.xlsx','kc'),('1059e4ff-FSA-MEYER-v4-Meyer.xlsx','meyer')]:
    wb=openpyxl.load_workbook(D+f,read_only=True)
    ws=wb['Досье']; it=ws.iter_rows(values_only=True); h=list(next(it)); ix={k:i for i,k in enumerate(h)}
    g=lambda r,k: (str(r[ix[k]]).strip() if r[ix[k]] not in (None,'','—') else '')
    c=collections.Counter(); inns={}
    for r in it:
        inn=g(r,'ИНН'); vr=float(g(r,'Выручка, руб') or 0)
        письмо=g(r,'Конвейер: Письмо: e-mail'); пп=g(r,'Почты (из деклараций)')
        torg='торговл' in g(r,'Выручка: пометка')
        posr=bool(g(r,'Посредник? (оформитель деклараций)'))
        pas=sum(1 for k in h if k.startswith('Паспорт:') and k not in ('Паспорт: уверенность','Паспорт: источники','Паспорт: откуда') and g(r,k))
        pasconf=g(r,'Паспорт: уверенность')
        povod=bool(g(r,'Строят (ЕГРЗ 2025+)') or g(r,'Поводы (новости)') or g(r,'Паспорт: свежая новость') or g(r,'Паспорт: расширение'))
        kcpr=bool(g(r,'Паспорт: КЦ-признак (воздух/газы)') or g(r,'Паспорт: газы') or g(r,'Паспорт: энергохозяйство'))
        sait=bool(g(r,'Конвейер: Сайт') or g(r,'Ночь: сайт (ИНН на сайте)'))
        lpr=bool(g(r,'Конвейер: ЛПР: e-mail'))
        fresh=int(g(r,'За 12 мес.') or 0)>0
        c['всего']+=1
        c['выручка от 100 млн']+= vr>=1e8
        c['выручка 30-100 млн']+= 3e7<=vr<1e8
        c['выручка нет']+= vr==0
        c['пометка торговля']+=torg
        c['посредник в контактах декларации']+=posr
        c['почта для письма (конвейер)']+=bool(письмо)
        c['только почта из декларации']+= (not письмо) and bool(пп)
        c['нет почты вовсе']+= (not письмо) and not пп
        c['почта ЛПР именная']+=lpr
        c['сайт подтверждён']+=sait
        c['паспорт: 3+ полей']+= pas>=3
        c['паспорт: 1-2 поля']+= 1<=pas<3
        c['паспорт: нет']+= pas==0
        c['паспорт уверенность высокая']+= pasconf=='высокая'
        c['повод (ЕГРЗ/новость/расширение)']+=povod
        c['КЦ-признак (воздух/газы/энерго)']+=kcpr
        c['декларация за 12 мес.']+=fresh
        tier = 'A' if (письмо or пп) and pas>=3 and not torg else 'B' if (письмо or пп) and (pas>=1 or g(r,'Конвейер: Описание (по сайту)')) and not torg else 'C' if (письмо or пп) else 'D'
        c['ярус '+tier]+=1
        inns[inn]=[tier,vr,bool(письмо)]
    out[tag]=inns
    print('=====',tag); [print('  %-40s %d'%(k,v)) for k,v in c.items()]
json.dump(out,open(S+'inns.json','w'))
