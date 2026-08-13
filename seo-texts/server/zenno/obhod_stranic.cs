// Кубик ZennoPoster 7.9: обход САЙТОВ пачкой в ОДНОМ инстансе.
//
// Зачем: дельфин поднимает профиль на КАЖДУЮ страницу (10-30 с) и по факту доходит только
// до главной. Зенка держит инстанс и проходит сайт целиком: главная -> карта сайта ->
// контакты -> второй уровень. Замер 12.08: 100 адресов по 9,7 с каждый.
//
// ПАЧКОЙ (владелец 13.08: «он запускает всё равно на 1 сайт 1 профиль?», «и этим глушит
// процессор»). ZennoPoster поднимает браузер на КАЖДОЕ выполнение шаблона, и при одной
// компании за выполнение процессор уходит на пересоздание инстансов, а не на работу.
// Поэтому кубик берёт из очереди подряд KOMPANIY_ZA_RAZ компаний и обходит их в одном
// браузере, очищая куки и кэш между ними. Восемь потоков по десять компаний — это восемь
// браузеров на восемьдесят сайтов вместо восьмидесяти браузеров.
//
// Ограничения 7.9, проверены на сервере (не менять на «привычное»):
//   * LoadProfile и DocumentText НЕ работают -> HTML берём FindElementByTag("html",0)
//     и GetAttribute("outerhtml");
//   * общий замок для файлов и списков — SyncObjects.ListSyncer.
//
// НАСТРАИВАТЬ В ПРОЕКТЕ НИЧЕГО НЕ НАДО: папки, очередь и прокси кубик находит сам.
// Списки sajty/proxy и переменные проекта используются, только если они уже заведены.
// От оператора — число потоков и повтор выполнения.
//
// ПАПКА ОБМЕНА (создаётся сама): C:\seostat\drop\zenno
//   ochered.txt      — очередь «ИНН;адрес», наполняет zenno_most.py --ochered
//   proxy.txt        — обычные прокси построчно (нет файла -> идём напрямую)
//   proxy_mobile.txt — МОБИЛЬНЫЕ: на них переходим, когда сайт не дался с обычного
//   gotovo\          — результат, эту папку слушает zenno_most.py --priyom
//   ne_otkrylis.txt  — что не далось даже с мобильного
//
// ВЫХОД (на компанию): <ИНН>_0.html ... + <ИНН>.urls.txt (адреса в том же порядке)
// и <ИНН>.err.txt при ошибках. JSON не собираем: экранировать HTML в C# руками —
// источник битых файлов.

// БЕЗ BOM. System.Text.Encoding.UTF8 в .NET пишет метку порядка байтов, и она
// приезжает в НАЧАЛО первой строки .urls.txt: питон читает адрес как "\ufeffhttp://..."
// и страница теряет привязку. Поймано на первой же партии (13.08).
var bez_bom = new System.Text.UTF8Encoding(false);

// --- настройки: переменная проекта, если заведена, иначе умолчание ---
Func<string, string, string> nastroyka = delegate(string imya, string po_umolchaniyu)
{
    try
    {
        string v = project.Variables[imya].Value;
        if (!string.IsNullOrEmpty(v)) return v;
    }
    catch { }        // переменной в проекте нет — штатный случай, не ошибка
    return po_umolchaniyu;
};

string koren_obmena = nastroyka("papka_obmena", @"C:\seostat\drop\zenno");
string papka = nastroyka("papka_vyhod", System.IO.Path.Combine(koren_obmena, "gotovo"));
string fajl_ocheredi = nastroyka("fajl_ocheredi",
                                 System.IO.Path.Combine(koren_obmena, "ochered.txt"));
string fajl_proxy = nastroyka("fajl_proxy",
                              System.IO.Path.Combine(koren_obmena, "proxy.txt"));
string fajl_proxy_mob = nastroyka("fajl_proxy_mobile",
                                  System.IO.Path.Combine(koren_obmena, "proxy_mobile.txt"));
System.IO.Directory.CreateDirectory(koren_obmena);
System.IO.Directory.CreateDirectory(papka);
if (!System.IO.File.Exists(fajl_ocheredi))
    System.IO.File.WriteAllText(fajl_ocheredi, "", bez_bom);

int predel = 3;
// Сколько внутренних страниц брать. Было 3 (владелец 13.08: «страниц написано много
// где 4, это какое-то ограничение?» — да, 3 внутренних плюс главная). Питоновский
// краул берёт до 10 и добирает второй уровень, поэтому поднимаем до 6: Зенка должна
// быть не хуже дельфина, а лучше. Чтобы глубина не съела скорость, ниже стоит
// правило остановки — набрали контакты, дальше не копаем.
if (!int.TryParse(nastroyka("stranic_max", "6"), out predel) || predel <= 0) predel = 6;
int za_raz = 10;
if (!int.TryParse(nastroyka("kompaniy_za_raz", "10"), out za_raz) || za_raz <= 0) za_raz = 10;

// --- прокси: читаем оба файла один раз на выполнение ---
Func<string, List<string>> chitat_proxy = delegate(string put)
{
    var l = new List<string>();
    try
    {
        if (System.IO.File.Exists(put))
            foreach (string s in System.IO.File.ReadAllLines(put))
                if (s.Trim().Length > 0 && !s.Trim().StartsWith("#")) l.Add(s.Trim());
    }
    catch { }
    return l;
};
var proxy_obychnye = chitat_proxy(fajl_proxy);
var proxy_mobilnye = chitat_proxy(fajl_proxy_mob);
try
{
    if (proxy_obychnye.Count == 0 && project.Lists["proxy"].Count > 0)
        foreach (string s in project.Lists["proxy"]) if (s.Trim().Length > 0)
            proxy_obychnye.Add(s.Trim());
}
catch { }
var sluchay = new Random(Guid.NewGuid().GetHashCode());

// --- взять следующее задание из очереди (атомарно для всех потоков) ---
Func<string> sleduyushchee = delegate()
{
    string s = "";
    lock (SyncObjects.ListSyncer)
    {
        bool iz_spiska = false;
        try
        {
            if (project.Lists["sajty"].Count > 0)
            {
                s = project.Lists["sajty"][0];
                project.Lists["sajty"].RemoveAt(0);
                iz_spiska = true;
            }
        }
        catch { }    // списка sajty нет — работаем прямо с файлом
        if (!iz_spiska)
        {
            try
            {
                var vse = System.IO.File.ReadAllLines(fajl_ocheredi, bez_bom);
                int pervaya = -1;
                for (int i = 0; i < vse.Length; i++)
                    if (vse[i].Trim().Length > 0) { pervaya = i; break; }
                if (pervaya >= 0)
                {
                    s = vse[pervaya].Trim();
                    var ostatok = new List<string>();
                    for (int i = 0; i < vse.Length; i++)
                        if (i != pervaya && vse[i].Trim().Length > 0) ostatok.Add(vse[i]);
                    System.IO.File.WriteAllLines(fajl_ocheredi, ostatok.ToArray(),
                                                 bez_bom);
                }
            }
            catch (Exception e)
            {
                project.SendWarningToLog("очередь недоступна: " + e.Message, true);
            }
        }
    }
    return s;
};

string inn = "";
var oshibki = new System.Text.StringBuilder();

// Открыть адрес и вернуть HTML. Пустая строка = не открылось.
Func<string, string> vzyat = delegate(string adres)
{
    try
    {
        instance.ActiveTab.Navigate(adres, "");
        instance.ActiveTab.WaitDownloading();
        var he = instance.ActiveTab.FindElementByTag("html", 0);
        if (he == null || he.IsVoid)
        {
            oshibki.AppendLine(adres + " -> пустой документ");
            return "";
        }
        return he.GetAttribute("outerhtml");
    }
    catch (Exception e)
    {
        oshibki.AppendLine(adres + " -> " + e.Message);
        return "";
    }
};

// Страница считается взятой, если это не заглушка антибота и не пустышка.
Func<string, bool> godnaya = delegate(string h)
{
    if (h == null || h.Length < 600) return false;
    string n = h.ToLower();
    if (n.Contains("just a moment") || n.Contains("checking your browser")
        || n.Contains("proxy authentication required")
        || n.Contains("доступ ограничен") || n.Contains("are you not a robot")) return false;
    return true;
};

// Карта сайта: robots.txt -> Sitemap, иначе /sitemap.xml. Питон её здесь не добудет —
// сайт закрыт как раз для него, поэтому карту берём тем же браузером.
Func<string, List<string>> iz_karty = delegate(string koren)
{
    var naydeno = new List<string>();
    var karty = new List<string>();
    string rob = vzyat(koren + "/robots.txt");
    if (rob.Length > 0)
        foreach (System.Text.RegularExpressions.Match m in
                 System.Text.RegularExpressions.Regex.Matches(rob, "Sitemap:\\s*(\\S+)",
                     System.Text.RegularExpressions.RegexOptions.IgnoreCase))
        {
            string s = m.Groups[1].Value.Trim();
            if (s.StartsWith("http") && !karty.Contains(s)) karty.Add(s);
        }
    if (karty.Count == 0) karty.Add(koren + "/sitemap.xml");

    var slova_k = new string[] { "contact", "kontakt", "svyaz", "about", "o-kompanii",
                                 "o-nas", "rukovod", "staff", "team", "sotrudnik" };
    int razobrano = 0;
    for (int k = 0; k < karty.Count && razobrano < 3 && naydeno.Count < 6; k++)
    {
        string xml = vzyat(karty[k]);
        razobrano++;
        if (xml.Length == 0) continue;
        foreach (System.Text.RegularExpressions.Match m in
                 System.Text.RegularExpressions.Regex.Matches(xml, "<loc>([^<]{1,300})</loc>",
                     System.Text.RegularExpressions.RegexOptions.IgnoreCase))
        {
            string loc = m.Groups[1].Value.Trim();
            string nl = loc.ToLower();
            if (nl.EndsWith(".xml") && !karty.Contains(loc) && karty.Count < 5)
            {
                karty.Add(loc);      // карта карт
                continue;
            }
            bool nuzhna = false;
            foreach (string s in slova_k) if (nl.Contains(s)) { nuzhna = true; break; }
            if (nuzhna && !naydeno.Contains(loc) && naydeno.Count < 6) naydeno.Add(loc);
        }
    }
    return naydeno;
};

// Почты на собранных страницах: по ним работает правило остановки. Тот же принцип,
// что в питоне («не первые N страниц, а пока приносят новые контакты»).
var re_pochta = new System.Text.RegularExpressions.Regex(
    "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,6}");
Func<string, HashSet<string>> pochty_so_stranicy = delegate(string h)
{
    var n = new HashSet<string>();
    foreach (System.Text.RegularExpressions.Match m in re_pochta.Matches(h ?? ""))
    {
        string e = m.Value.ToLower();
        if (e.EndsWith(".png") || e.EndsWith(".jpg") || e.EndsWith(".gif")
            || e.EndsWith(".webp") || e.EndsWith(".svg")) continue;
        n.Add(e);
    }
    return n;
};

var slova = new string[] { "contact", "kontakt", "svyaz", "about", "o-kompanii",
                           "o-nas", "company", "rukovod", "staff", "team",
                           "sotrudnik", "rekvizit" };
var ugadki = new string[] { "/contacts/", "/kontakty/", "/contact/", "/about/",
                            "/o-kompanii/", "/company/staff/", "/company/", "/rukovodstvo/" };
var re = new System.Text.RegularExpressions.Regex(
    "href\\s*=\\s*[\"']([^\"'#]{1,180})[\"']",
    System.Text.RegularExpressions.RegexOptions.IgnoreCase);

int vsego_stranic = 0, vsego_kompaniy = 0, s_mobilki = 0;

for (int nomer = 0; nomer < za_raz; nomer++)
{
    string stroka = sleduyushchee();
    if (stroka.Length == 0)
    {
        if (nomer == 0) project.SendInfoToLog("очередь пуста — поток завершён", true);
        break;
    }
    var chasti = stroka.Split(';');
    inn = chasti[0].Trim();
    string url = (chasti.Length > 1 ? chasti[1] : chasti[0]).Trim();
    if (url.Length == 0) continue;
    if (!url.StartsWith("http")) url = "http://" + url;
    oshibki.Length = 0;

    // между компаниями чистим сессию и меняем адрес выхода
    instance.ClearCookie();
    instance.ClearCache();
    if (proxy_obychnye.Count > 0)
        instance.SetProxy(proxy_obychnye[sluchay.Next(proxy_obychnye.Count)]);

    var adresa = new List<string>();
    var htmly = new List<string>();

    string glavnaya = vzyat(url);
    // ПОВТОР С МОБИЛЬНОГО (владелец 13.08). Датацентр-адреса режут не только справочники:
    // часть корпоративных сайтов сидит за антиботом, который пропускает мобильную сеть и
    // молча отдаёт пустоту всем остальным. Пробуем ровно один раз и только при провале —
    // мобильных адресов мало и они платные.
    if (!godnaya(glavnaya) && proxy_mobilnye.Count > 0)
    {
        instance.SetProxy(proxy_mobilnye[sluchay.Next(proxy_mobilnye.Count)]);
        instance.ClearCookie();
        string vtoraya = vzyat(url);
        if (godnaya(vtoraya)) { glavnaya = vtoraya; s_mobilki++; }
    }

    if (godnaya(glavnaya))
    {
        adresa.Add(url);
        htmly.Add(glavnaya);

        Uri baza = new Uri(url);
        string koren = baza.Scheme + "://" + baza.Host;
        var vidno = new HashSet<string>();
        var snachala = new List<string>();
        var potom = new List<string>();

        foreach (System.Text.RegularExpressions.Match m in re.Matches(glavnaya))
        {
            string ssylka = m.Groups[1].Value.Trim();
            if (ssylka.Length == 0) continue;
            string nizhniy = ssylka.ToLower();
            if (nizhniy.StartsWith("mailto:") || nizhniy.StartsWith("tel:")
                || nizhniy.StartsWith("javascript:")) continue;
            bool podhodit = false;
            foreach (string s in slova) if (nizhniy.Contains(s)) { podhodit = true; break; }
            if (!podhodit) continue;
            // технические эндпоинты движков: wp-json/oembed, feed, печатные версии.
            // Они содержат «contact» в параметрах и лезли в обход пустышками.
            if (nizhniy.Contains("wp-json") || nizhniy.Contains("oembed")
                || nizhniy.Contains("/feed") || nizhniy.Contains("?url=")
                || nizhniy.Contains("print=") || nizhniy.EndsWith(".xml")
                || nizhniy.EndsWith(".pdf") || nizhniy.EndsWith(".jpg")
                || nizhniy.EndsWith(".png")) continue;
            string polnyy;
            try { polnyy = new Uri(baza, ssylka).ToString(); } catch { continue; }
            try { if (new Uri(polnyy).Host != baza.Host) continue; } catch { continue; }
            if (polnyy == url || !vidno.Add(polnyy)) continue;
            // контактные первыми: по замеру окупаемости 13.08 страница контактов даёт
            // 853 адреса из 2157, «о компании» — 289, руководство — 25
            if (nizhniy.Contains("contact") || nizhniy.Contains("kontakt")
                || nizhniy.Contains("svyaz")) snachala.Add(polnyy);
            else potom.Add(polnyy);
        }
        snachala.AddRange(potom);

        foreach (string s in iz_karty(koren))
            if (vidno.Add(s)) snachala.Add(s);

        bool est_kontakt = false;
        foreach (string s in snachala)
        {
            string n = s.ToLower();
            if (n.Contains("contact") || n.Contains("kontakt")) { est_kontakt = true; break; }
        }
        if (!est_kontakt)
            foreach (string p in ugadki)
                if (vidno.Add(koren + p)) snachala.Add(koren + p);

        int vzyato = 0;
        var vtoroy = new List<string>();
        var nashli_pochty = pochty_so_stranicy(glavnaya);
        foreach (string k in snachala)
        {
            if (vzyato >= predel) break;
            // ПРАВИЛО ОСТАНОВКИ: две разные почты уже есть и хотя бы одна внутренняя
            // страница пройдена — дальше копать незачем. Иначе глубина в 6 страниц
            // умножилась бы на все сайты, включая те, где контакты лежат на первой же.
            if (nashli_pochty.Count >= 2 && vzyato >= 1) break;
            string h = vzyat(k);
            vzyato++;
            if (!godnaya(h)) continue;
            adresa.Add(k);
            htmly.Add(h);
            foreach (string e in pochty_so_stranicy(h)) nashli_pochty.Add(e);

            // второй уровень: у мульти-офисных сайтов карточки отделов и филиалов лежат
            // ПОД страницей контактов, и с главной на них ссылок нет
            string nk = k.ToLower();
            if (!(nk.Contains("contact") || nk.Contains("kontakt") || nk.Contains("staff")
                  || nk.Contains("rukovod"))) continue;
            foreach (System.Text.RegularExpressions.Match m in re.Matches(h))
            {
                string ss = m.Groups[1].Value.Trim();
                string ns = ss.ToLower();
                if (ns.StartsWith("mailto:") || ns.StartsWith("tel:")
                    || ns.StartsWith("javascript:")) continue;
                bool ok2 = false;
                foreach (string s in slova) if (ns.Contains(s)) { ok2 = true; break; }
                if (!ok2) continue;
                string p2;
                try { p2 = new Uri(baza, ss).ToString(); } catch { continue; }
                try { if (new Uri(p2).Host != baza.Host) continue; } catch { continue; }
                if (vidno.Add(p2)) vtoroy.Add(p2);
            }
        }

        int vzyato2 = 0;
        foreach (string k in vtoroy)
        {
            if (vzyato2 >= predel) break;
            if (nashli_pochty.Count >= 3) break;   // второй уровень нужен, пока пусто
            string h = vzyat(k);
            vzyato2++;
            if (!godnaya(h)) continue;
            adresa.Add(k);
            htmly.Add(h);
            foreach (string e in pochty_so_stranicy(h)) nashli_pochty.Add(e);
        }
    }

    // Запись. Порядок важен: сперва html, ПОТОМ .urls.txt — приёмник ориентируется на
    // список адресов, и появись он раньше страниц, разбор подхватил бы половину.
    for (int i = 0; i < htmly.Count; i++)
        System.IO.File.WriteAllText(
            System.IO.Path.Combine(papka, inn + "_" + i.ToString() + ".html"),
            htmly[i], bez_bom);
    if (htmly.Count > 0)
    {
        System.IO.File.WriteAllLines(
            System.IO.Path.Combine(papka, inn + ".urls.txt"), adresa.ToArray(),
            bez_bom);
        vsego_kompaniy++;
        vsego_stranic += htmly.Count;
    }
    else
    {
        // не далось даже с мобильного: пишем отдельно и НЕ возвращаем в очередь —
        // молчаливый повтор гонял бы мёртвый адрес по кругу
        lock (SyncObjects.ListSyncer)
            System.IO.File.AppendAllText(
                System.IO.Path.Combine(koren_obmena, "ne_otkrylis.txt"),
                inn + ";" + url + ";" + DateTime.Now.ToString("yyyy-MM-dd HH:mm") + "\r\n",
                bez_bom);
    }
    if (oshibki.Length > 0)
        System.IO.File.WriteAllText(
            System.IO.Path.Combine(papka, inn + ".err.txt"),
            oshibki.ToString(), bez_bom);

    project.SendInfoToLog(inn + ": страниц " + htmly.Count.ToString() + ", " + url, true);
}

project.SendInfoToLog("пачка: компаний " + vsego_kompaniy.ToString()
                      + ", страниц " + vsego_stranic.ToString()
                      + ", спасено мобильным " + s_mobilki.ToString(), true);
return vsego_stranic;
