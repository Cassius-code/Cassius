# RD CONTROL

Bitta bot: zaderjka nazorati, stavka, «доброе утро», tanaffus, jarimalar, kassa va haftalik oyliklar, Push, hisobotlar.

## Nima qiladi

- **🚨 Nazorat.** Mijoz (vositachi bot) yozsa va 20 daqiqada javob bo'lmasa, «Проёб»ga «задержка» va
  «✅ Выполнено» tugmasi boradi. Faqat ish vaqtida hisoblanadi: kechasi kelgan xabarlar sanalmaydi.
  Javob — har qanday xodim xabari, papka akkauntidan yozilgani ham (Push yuborgan xabarlar sanalmaydi).
  Xodim yozgandan keyin bot yozsa — bu mijozning yangi xabari, unga ham javob kerak.
  Ish vaqtida guruhlar har 2 soniyada tekshiriladi (akkaunt «online» qilinmaydi): bot jonli kelgan har xabar
  raqamini eslab qoladi, guruhda tushib qolgan raqam bo'lsa — faqat o'sha xabarlarni olib, tartib bilan ishlaydi.
  Xodim javobi kech topilsa — kutish javob vaqtida yopiladi (noto'g'ri «задержка» va jarima bo'lmaydi).
  Lid xabarini qayta ishlash «Проёб»ga yozishni kutmaydi: Telegram botni sekinlashtirsa ham xabarlar o'z vaqtida.
  Bir-biriga yaqin kechikkan lidlar — 40 soniya kutib, bitta xabarda; keyingisi — pastga yangi xabar.
  Mijoz ketma-ket yozsa (birinchi xabaridan 5 daqiqa ichida) — zaderjka oxirgi xabaridan hisoblanadi
  (🚨 Nazorat → 🔁 Ketma-ket: 3/4/5/7/10 daqiqa yoki o'chiq).
  «Проёб»ga kim yozadi: 🤖 bot yoki 🔑 asosiy akkaunt (⚙️ → ✍️). Asosiy akkaunt guruhda anonim admin bo'lsa —
  xabarlar «Проёб» nomidan. Bunda «✅ Выполнено» tugmasi bo'lmaydi (zaderjka javob bilan o'zi yopiladi).
  Lid statusi ⚡/💊 (Клоун, Мариновка) — zaderjka emas: status qo'yilsa kutish bekor, ochiq zaderjka yopiladi.
  Xodimning `/status` buyrug'i va vositachi botning status menyusi mijoz xabari hisoblanmaydi.
  **Papkalar:** 🚨 Nazorat → 📁 Papkalar — asosiy akkauntdagi papkalar ro'yxati; ➕ — qo'shish (guruhlari o'zi
  keladi), ✅ — ochish: 👤 javob beradigan xodimlar, nazorat, o'chirish. Har papkada 🔥 lidlar soni.
- **🎬 Stavka.** Yangi chatda birinchi stavka 20 daqiqada, keyingilari ham 20 daqiqada kelishi kerak.
  Kelmasa, «ставка» deb eslatadi (eng ko'pi 3 marta). Xodimning o'z videosi ham stavka hisoblanadi.
  3 ta stavka kelsa — stavka tugaydi. Kelmasa — 3-eslatmadan keyin stavka tugaydi va keyingi xabarlar oddiy
  zaderjka hisoblanadi (vaqt chegarasi yo'q). Stavka paytida lid ham, xodim ham nima yozsa — zaderjka emas.
  Topik ma'lumoti kech kelsa ham (yangi lid aniqlanmay qolsa) — birinchi stavka videosi kelganda yoki topik
  ochilgan vaqti bilinganda stavka o'sha paytdan boshlanadi. (Eski versiyada «🔒 Qattiq rejim» tugmasi aslida
  stavkani o'chirardi — yangilangach stavka bir marta o'zi qayta yoqiladi.)
- **🔔 Eslatmalar** (🚨 Nazorat → 🔔), faqat xodimlarga, «Проёб»da, faqat ish vaqtida:
  - 🆕 **Yangi lid jim** — bugun kelgan yangi lidga stavkadan keyin 2 soat hech kim yozmasa (lid ham, xodim ham,
    Push ham) — har RD alohida xabar, o'sha kuni ishdagi xodimlar belgilanadi.
  - 💳 **To'lov eslatmasi** — xodim kartani yubordi (/rek /dep /cash), keyin 15 daqiqa hech kim yozmadi —
    kartani yuborgan xodim belgilanadi: «уточните у клиента оплату». Mijozga hech narsa ketmaydi.
  Vaqtlar (yoki o'chirish) — shu ekranda.
- **🌙 Kun oxiri.** Ish vaqti tugagach (23:01) javobsiz chatlar ro'yxati «Проёб»ga boradi:
  «доведите работу до конца». Ertalab ular uchun zaderjka yozilmaydi.
- **💸 Jarimalar** (🚨 Nazorat → 💸 Jarimalar) — bitta jadval, har biri aniq summa, alohida yoqiladi:
  - ⏰ **Zaderjka javobsiz qolsa** — «задержка» → 15 daqiqa → eslatma (xodimlar belgilanadi) → 5 daqiqa → jarima;
  - 👥 **Ko'p lid birdaniga** — papkada N ta lid bir vaqtda javobsiz → kuniga K marta kechiriladi → G daqiqa → jarima
    (summa 0 — o'chiq; papkaga alohida summa ham mumkin);
  - 🕘 **Kech qolish** (💸 → 🕘) — narx: har daqiqaga (masalan `2`) yoki pog'ona (`10=2, 30=5`); necha daqiqa
    bepul; hisob: faqat bepuldan ortig'i (25 daq kech, 5 bepul, 2 $ → 40 $) yoki hamma daqiqalar (→ 50 $).
    Xodim kelganda «Проёб»da: «🕘 @xodim, вы опоздали на 25 мин — вам штраф 40 $»;
  - ✍️ **Qo'lda** — «Проёб»da `@xodim штраф 5` (yoki xodim xabariga javob qilib `штраф 5`).
  Jarima o'sha kuni papkada ishlayotgan xodimlarga («доброе утро» yoki lidga yozgan); hech kim kelmagan bo'lsa —
  dam olmayotgan hammaga. «Проёб»da qisqa xabar: «💸 @xodim, вам штраф 5 $ за задержку».
  Guruhdagi e'lon yoki qoida (masalan «bugun 10 000 kassa qilganga 20 $ бонус») jarima/bonus deb o'qilmaydi —
  faqat xodim ko'rsatilgan qisqa buyruq.
- **🧹 «Проёб»ni tozalash.** Zaderjka xabari — xodim javob berganidan 10 daqiqa keyin o'chadi; boshqa avtomat
  xabarlar (soviyotgan va jim yangi lidlar, to'lov eslatmasi, kechikish, Push tugadi, jarima ogohlantirishi,
  stavka) — 1 soatdan keyin. Vaqtni o'zingiz
  tanlaysiz: 🚨 Nazorat → 🧹 Tozalash (0 — o'chmaydi). Jarima yozilgan xabar («💸 штраф», jarimali
  kechikish) o'chmaydi. Buyruqqa javoblar va doska ham o'chmaydi; hisob botda qoladi. Botga guruhda «Xabarlarni
  o'chirish» huquqi kerak.
- **📌 Doska.** «Проёб» tepasida qadalgan «Задержки сейчас»: har RD — hozir nechta lid limitdan oshib javobsiz
  (🟢 / 🟡 / 🔴). Hamma ko'radi, pul yo'q. Son o'zgarsa — o'sha xabar joyida yangilanadi (kamida 20 soniyada bir,
  Telegram guruhga ko'p yozishni cheklaydi). 🚨 Nazorat → 📌 Doska (yoqish / o'chirish). Botga guruhda «Xabarlarni
  qadash» huquqi kerak.
- **🙋 Ishga kelish.** Xodim «доброе утро» yozsa YOKI lidga yoza boshlasa — ishga kelgan (qaysi biri oldin bo'lsa).
  Kech qolish shu vaqtdan; kech qolsa «Проёб»ga: «🕘 @xodim, вы опоздали на 25 мин — вам штраф 40 $»
  (tagida mayda: «начало в 10:25 · по графику 10:00»).
  Ish boshlanib 15 daqiqada hali ko'rinmaganlarga eslatma boradi; lidga yozib ishlayotganlarga — yo'q.
- **☕ Tanaffus.** «атайду» / «перерыв» — boshlanadi, «тут» / «вернулся» / «вернулась» — tugaydi. Vaqt oshsa,
  faqat eslatma boradi.
- **🏆 Haftalik ball** (👥 Xodimlar → 🏆). Har xodimga 0–100: ⚡ tezlik · 🚨 zaderjka · 💳 karta · 🕘 intizom (har
  biri 25). 🔥 — ketma-ket zaderjkasiz ish kunlari, bir qator maslahat. Haftada 20 tadan kam javob — ball yo'q.
  «Проёб»da /statistika — ball bo'yicha 🥇🥈🥉; xodim o'z balini haftalik zp xabarida ko'radi. Pulga bog'lanmagan.
- **💵 Kassa.** Kassa — cheklar yig'indisi (1950 + 2600 = 4 550); zp — $ da. «Проёб»dagi cheklar, jarima, bonus, avanslar.
  - **Hisobotni botning o'ziga yozish mumkin:** tepasida ism bilan, masalan `Baxa` / `rd 19.10` / `1950` / `2600`.
    Ism bo'lmasa yoki bot tanimasa — «Kimning hisoboti?» deb so'raydi, tagida «➕ Yangi xodim» tugmasi bor
    (ism yozilgan bo'lsa — o'sha ism bilan qo'shadi, bo'lmasa — ismni so'raydi).
    Telefon raqami (`+998 90 123 45 67`, `998901234567`, `90 123 45 67`) hisobot hisoblanmaydi.
    Ism notanish bo'lsa — «➕ Yangi xodim: Baxa» tugmasi chiqadi (shunday tanishtirasiz). Jarima ham:
    `@ivan штраф 5`. Guruhda ham xuddi shunday.
  - Bosh menyuda — 💰 **Cash**: dushanbadan beri jami kassa ($, faqat egaga) va «Задержки сейчас» — har RD
    da hozir nechta zaderjka (🟢 yo'q · 🟡 bor · 🔴 ko'p). Menyu o‘z joyida yangilanadi (5 soniyada bir; tugma
    bosilgan paytda tegmaydi).
    Kassa bo'limida — cheklar yig'indisi, har birining $ i va jami, 🏆 top 3.
  - **🏆 Umumiy reyting** kassa bo'limida: boshlang'ich (oldingi haftalar) kassa + 19.10 dan keyingi cheklar.
    Guruhda `/topall`. Boshlang'ich raqamlar: 🏆 Reyting → ♾ Hammasi → 📌.
  - **🧮 Haftani hisoblash.** Hafta (Du–Ya) tugagach bosasiz. Bot o'tgan haftadagi foizlarni ko'rsatadi:
    «Bayzed: Bayzed 41% · Siz 14% · Artur qolgani». O'zgarmagan bo'lsa — bitta tugma. O'zgargan bo'lsa —
    ismni bosib yangi sonni yozasiz (masalan `41 14`). Yangi xodim bo'lsa, bot o'zi so'raydi.
    O'zgarish faqat shu haftadan: o'tgan haftalar buzilmaydi. Hafta hisoblanmaguncha zp ko'rinmaydi.
  - **🤝 Ulushlar.** Masalan «Baxa oyligidan 5% → Bayzed». Kim to'laydi: xodimdan ushlanadi, siz yoki Artur.
  - **📋 To'lov ro'yxati.** Haftalik: kimga qancha, «✅ To'landi». Keyingi hafta noldan.
  - **✅ Kunni yopish.** Hamma hisobot tushgach bosasiz. Yopilgan kunni faqat siz o'zgartira olasiz.
    Yopilgan kunga yangi hisobot kelsa, sizga xabar keladi.
  - **📜 Tarix.** Kim, qachon, nimani o'zgartirgani (eski → yangi).
  - **🧮 Tekshiruv.** Hisobotda: Kassa = Artur + xodimlar + ulushlar + sizga ✅.
  - O'tgan hafta bilan solishtirish (↑ / ↓ %), 🗓 Oy yakuni, kunlar → akkauntlar → cheklar.
  - Zp hisoblash usuli: **tugma bilan** (odatiy) / **avtomatik** / **o'chiq** (o'zingiz hisoblaysiz).
  - Har hisobotdan keyin sizga xodimning shu kungi xulosasi keladi (eski kassa botidagidek):
    `Adam` / `Дата: 19.10` / `Касса: 17,100` / `Кол-во рд: 8` / `Касса ($): 64$`. Shu kunga yana hisobot kelsa —
    eskisi o'chadi, kunning jami bilan yangisi keladi.
  - Pul amallari (to'landi, avans, ulushlar, foizlar) — faqat siz. Adminlar cheklarni tuzatadi.
  - Xodim faqat o'z zp sini ko'radi, so'rov avval sizga keladi. Daromadingizni faqat siz ko'rasiz.
- **📣 Push.** Har papka o'z akkauntidan, faqat qo'lda (🚀). Kimga va qaysi tartibda — soatga qarab:
  🌅 ertalab (13:00 gacha) — bugun gaplashmaganlar, kechagidan boshlab eskiroqlariga;
  ☀️ kunduzi — faqat bugun gaplashganlar: ertalabkilar → jim turganlar (30/60 daq) → hozirgina yozishganlar;
  🌙 kechqurun (19:00 dan) — avval bugungilar, keyin kechagi va eskiroqlar.
  Baza — 28.08.2026 dan keyin o'zi yozgan har bir lid (yangi kelgani ham, eskisi ham). Bot ularni bir marta to'liq
  tekshiradi (tugagach xabar keladi; qayta: 📣 Push → ⚙️ → 🔍 Bazani tekshirish). Vaqtlar va sana: 📣 Push → ⚙️.
  CRM'ning o'z xabarlari («Статус: …», «Реквизиты отправлены», /rek /status buyrug'iga javob va menyusi) «lid o'zi
  yozdi» hisoblanmaydi. Yangilangandan keyin baza bir marta qaytadan, shu qoida bilan yig'iladi.
  ⏹ bosilsa — Push to'xtaydi va darhol «▶️ Davom ettirish» chiqadi: faqat hali olmaganlarga, ikki marta yuborilmaydi.
  Papkaga akkaunt: 📣 Push → 📁 Papkalar → papka → 📲 Akkaunt (➕ yangisini shu yerning o'zida ulash mumkin).
  Push ketayotganda sonini o'zgartirsangiz (⚙️ → 🔢 Soni yoki papkaning o'z soni) — darhol shu son bilan davom etadi.
  «Проёб»da Push paneli (hamma ko'radi): nima ketyapti (matn / ovozli …), har RD — nechtadan nechtasi. Tugagach —
  shu xabarga javob qilib xodimlar belgilanadi («Пуш завершён … будьте на связи»), panel 5 daqiqada o'chadi.
  O'chirish: 📣 Push → ⚙️ → 👥 Guruhda panel.
  Push paytida bot yangilansa (GitHub'ga yuklasangiz) yoki qayta ishga tushsa — Push o'zi joyidan davom etadi:
  yuborilganlarga qayta yubormaydi, son o'sha. ⏹ bilan to'xtatilgani davom etmaydi.
  Telegram akkauntga «kuting» desa (FloodWait) — o'sha papka kutadi (30 daqiqagacha), ekranda «⏳ RD 9 → 12:44»,
  keyin o'zi davom etadi (sekinroq); boshqa papkalar to'xtamaydi. Kutish uzoqroq bo'lsa — papka to'xtaydi va Push
  ekranida «▶️ Davom ettirish — qolgan N ta» chiqadi: faqat yetmay qolgan papkalar o'z sonigacha yuboriladi.
- **📊 Hisobotlar.** Faqat buyruq bilan: shaxsiy chatda `/hisobot`, guruhda `/statistika` (🥇🥈🥉 bilan).
- **📈 Tahlil** (📊 Hisobotlar → 📈). Hammasi faqat vaqt va kim yozgani bo'yicha — matn o'qilmaydi:
  - 🕐 Soatlar — har soatda nechta lid yozdi va nechtasi zaderjkaga tushdi (bugun / 7 kun, RD bo'yicha).
  - 💤 Qotib qolgan — N kun (3) hech kim yozmagan lidlar; 📉 Soviyotgan — mijoz odatdagidan 3 barobar uzoq jim.
    Soviyotganlarni bot «Проёб»da o'zi eslatadi (har RD alohida, xodim belgilanadi). Faqat kecha va undan oldin
    kelgan lidlar — bugun kelgan yangi lid «soviyotgan» hisoblanmaydi.
  - 💳 Kartalar — xodim topikda `/rek /dep /cash` yozsa, «lidga karta ketdi». Har RD: necha marta, qaysi lidga.
  - ⚡ Tezlik → karta va 🏆 G'oliblar — javob tezligi kartaga qanday ta'sir qiladi, eng yaxshi xodimlar formulasi.
  - 📣 Push natijasi (📣 Push → 🧾) — har Push'dan keyin 90 daqiqada nechta lid yozdi, 24 soatda nechtasiga karta ketdi.
  - Hammasini yoqish/o'chirish, kunlar va karta buyruqlari: ⚙️ Sozlamalar → 🧩 Qo'shimcha funksiyalar.
- **🛡 Akkaunt himoyasi.** Har kuni 09:00 dan keyin Push akkauntlar @SpamBot da tekshiriladi. Cheklov bo'lsa —
  o'sha akkauntdan Push to'xtaydi va sizga xabar keladi; cheklov olinsa — o'zi qaytadi.
  «🆕 Yangi lidlar» — shu kuni ochilgan topiklar (eski lid bugun yozsa, yangi hisoblanmaydi).
- **🌐 Til.** Har admin o'z tilini tanlaydi (bosh menyuning pastida). Savol va ogohlantirishlar ham har kimga
  o'z tilida boradi.
- **🧼 Toza chat.** Chatda doim bitta panel. «‹ Orqaga» — oldingi ekranga. Savol bir nechta egaga borsa —
  biringiz javob bersangiz, boshqalardagi nusxa o'chadi. Har hisobotga alohida xabar kelmaydi (guruhda 👌).
- **👥 Xodimlar.** ➕ qo'shish, ⚙️ → 🗑 O'chirish (yoki 🗄 Arxiv). ⚙️ Sozlamalar → 🧹 Tozalash: kassa / xodimlar /
  Push akkauntlarni o'chirib, boshidan kiritish (prays va boshlang'ich kassa qoladi).

Bot mijoz va xodim xabarlarining matnini o'qimaydi va saqlamaydi. Faqat kim yozgani va qachon yozgani
olinadi.

## O'rnatish — yangi bot sifatida (iPhone, taxminan 30 daqiqa)

Eng yaxshi vaqt — kechasi, ish vaqtidan tashqari.

**A. Eski botlardan ma'lumot olish (ular hali ishlab turadi)**
1. Kassa botining GitHub repozitoriyasida `bot.py` ni `kassa_bot_uchun/bot.py` bilan almashtiring
   (Add file → Upload files → Commit). 1–2 daqiqa kuting.
2. Kassa botga `/export` yozing → `kassa.db` fayli keladi.
3. Eski zaderjka botida: 📈 Hisobotlar → 💾 Zaxira nusxa → `.sqlite3` fayli keladi.

**B. Yangi bot va kod**
1. @BotFather → `/newbot` → nom → username → **token**ni nusxa oling.
2. Yangi botni oching va **Start** ni bosing (shunda u sizga yoza oladi).
3. iPhone «Fayllar» ilovasida ZIP ni bosing — papka ochiladi.
4. github.com → ➕ → New repository → nom (masalan `rdcontrol`) → Private → Create.
5. «uploading an existing file» → papkadagi hamma fayllarni tanlang (`kassa_bot_uchun` dan tashqari) → Commit.

**C. Eski botlarni to'xtatish** (bir akkaunt ikki joyda ishlamasligi kerak)
- Railway → eski zaderjka servisi → Deployments → oxirgi deploy → ⋮ → Remove.
- Kassa servisi uchun ham shunday. Volume'lar o'chmaydi, ma'lumot saqlanadi.

**D. Railway**
1. New Project → Deploy from GitHub repo → yangi repozitoriyani tanlang.
2. Variables:
   - `BOT_TOKEN` — yangi token
   - `ADMIN_IDS` — sizning Telegram ID (eski servis Variables'idan oling)
   - `API_ID`, `API_HASH` — eski zaderjka servisidan nusxa oling
   - `DATA_DIR` = `/data`
   - `TZ_NAME` = `Asia/Tashkent`
3. Volume: loyiha ekranida ➕ → Volume → shu servisga → Mount path `/data`.
4. Deploy tugagach bot sizga «✅ RD CONTROL ishga tushdi» deb yozadi.

**E. Yangi botda**
1. ⚙️ Sozlamalar → 📥 Ko'chirish → eski zaderjka botining zaxira faylini yuboring (forward).
2. Yana 📥 Ko'chirish → `kassa.db` ni yuboring.
3. ⚙️ → 🔑 Asosiy akkaunt → telefon, kod (va parol) bilan kiring. Zaxira faylda bu seans bo'lmaydi.
   Push akkauntlar fayl bilan birga keladi — ularga qayta kirish shart emas.
4. Yangi botni «Проёб» guruhiga qo'shing va **admin** qiling.
5. Bosh menyuda tekshiring: 🟢 Akkaunt · 🟢 Push · 🟢 «Проёб».
6. 👥 Xodimlar: bir odam ikki marta chiqsa — uni oching → ⚙️ → 🔗 Birlashtirish.
7. 💵 Kassa → 🧮 Haftani hisoblash: shu hafta foizlarini bir marta kiriting.
8. Xodimlarga ayting: yangi botda **Start** ni bossin (oylik so'rash uchun).

> `ADMIN_IDS` dagi odamlar «ega» hisoblanadi va hamma narsani ko'radi, sizning daromadingizni ham.
> Boshqa adminlarni bot ichidan qo'shing: ⚙️ → 👮 Adminlar.

## Egalikni yo'qotmaslik

- **Zaxira ega.** Railway → Variables → `ADMIN_IDS` ga ikkinchi akkauntingiz ID sini vergul bilan qo'shing:
  `111111111,222222222`. Ikkalasi ham to'liq ega.
- **Botning o'zidan:** ⚙️ → 👮 Adminlar → ➕ ID bo'yicha admin → nomini bosib 👑 ega darajasiga o'tkazing.
- **🔐 Tiklash kodi:** ⚙️ → 👮 Adminlar → 🔐 Tiklash kodi → kamida 8 belgili kod yozing va qog'ozga yozib qo'ying.
  Akkauntingiz yo'qolsa — yangi akkauntdan botga `/ega KOD` yozasiz va ega bo'lasiz. Kod bir marta ishlaydi.
  Noto'g'ri urinishlar haqida egalarga xabar boradi.
- Akkaunt o'g'irlangan bo'lsa: Railway → `ADMIN_IDS` dan eski ID ni olib tashlang (ma'lumot o'chmaydi).

## Buyruqlar

- Shaxsiy chat: `/menu` — panel, `/hisobot` — bugungi hisobot, `/id` — Telegram ID.
- «Проёб» guruhi:
  - `/proyob` — shu guruhni «Проёб» qilish
  - `/statistika` — hafta xulosasi va eng yaxshilar
  - `/topweek` — shu hafta kassasi, `/toplast` — o'tgan hafta, `/topall` — shu kungacha (boshlang'ich kassa bilan)
  - `/frozen` — 💤 qotib qolgan lidlar, `/cooling` — 📉 soviyotgan lidlar (har RD alohida xabar)
  - `/clean` — 🧹 javob berilgan «задержка» xabarlarini o'chirish (javob kutayotganlari qoladi)
    (bularni faqat ega yoki admin yoza oladi)
  - `/id` — guruh ID si

Bot guruhda xabarlarni ko'rishi uchun uni guruhda admin qiling.

## Zaxira

Har hafta sizga baza nusxasi keladi. Uni istalgan vaqtda olish mumkin: ⚙️ → 💾 Zaxira nusxa.
