# RD CONTROL

Bitta bot: zaderjka nazorati, stavka, «доброе утро», tanaffus, jarimalar, kassa va haftalik oyliklar, Push, hisobotlar.

## Nima qiladi

- **🚨 Nazorat.** Mijoz (vositachi bot) yozsa va 20 daqiqada javob bo'lmasa, «Проёб»ga «задержка» va
  «✅ Выполнено» tugmasi boradi. Faqat ish vaqtida hisoblanadi: kechasi kelgan xabarlar sanalmaydi.
  Javob — har qanday xodim xabari, papka akkauntidan yozilgani ham (Push yuborgan xabarlar sanalmaydi).
  Xodim yozgandan keyin bot yozsa — bu mijozning yangi xabari, unga ham javob kerak.
  Ish vaqtida guruhlar har 2 soniyada tekshiriladi (akkaunt «online» qilinmaydi): Telegram jonli
  yetkazmay qolgan xabar ham topilib, o'z vaqti bilan hisoblanadi.
  Bir-biriga yaqin kechikkan lidlar — 40 soniya kutib, bitta xabarda; keyingisi — pastga yangi xabar.
  Lid statusi ⚡/💊 (Клоун, Мариновка) — zaderjka emas: status qo'yilsa kutish bekor, ochiq zaderjka yopiladi.
  Xodimning `/status` buyrug'i va vositachi botning status menyusi mijoz xabari hisoblanmaydi.
  **Papkalar:** 🚨 Nazorat → 📁 Papkalar — asosiy akkauntdagi papkalar ro'yxati; ➕ — qo'shish (guruhlari o'zi
  keladi), ✅ — ochish: 👤 javob beradigan xodimlar, nazorat, o'chirish. Har papkada 🔥 lidlar soni.
- **🎬 Stavka.** Yangi chatda birinchi stavka 20 daqiqada, keyingilari ham 20 daqiqada kelishi kerak.
  Kelmasa, «ставка» deb eslatadi (eng ko'pi 3 marta). Xodimning o'z videosi ham stavka hisoblanadi.
  3 ta stavkadan keyin oddiy zaderjka nazorati boshlanadi.
- **🌙 Kun oxiri.** Ish vaqti tugagach (23:01) javobsiz chatlar ro'yxati «Проёб»ga boradi:
  «доведите работу до конца». Ertalab ular uchun zaderjka yozilmaydi.
- **💸 Jarima.** Har zaderjkaga emas. Ekranda oddiy tilda yozilgan: «papkada bir vaqtda N ta lid javobsiz qolsa…».
  Raqamni bosib o'zgartirasiz (masalan 5 ta lid, 10 daqiqa). Jarima shu kuni ishda bo'lgan xodimlarga yoziladi
  («доброе утро» yoki lidga yozgan); hech kim kelmagan bo'lsa — dam olmayotgan hammaga.
  Kech qolish: o'zingiz kiritasiz, masalan `0.5` (har daqiqa) yoki `10=2, 30=5`.
- **🙋 Ishga kelish.** Xodim «доброе утро» yozsa YOKI lidga yoza boshlasa — ishga kelgan (qaysi biri oldin bo'lsa).
  Kech qolish shu vaqtdan. «доброе утро» yozmagan bo'lsa, ish boshlanib 15 daqiqada eslatma boradi.
- **☕ Tanaffus.** «атайду» / «перерыв» — boshlanadi, «тут» — tugaydi. Vaqt oshsa, faqat eslatma boradi.
- **💵 Kassa.** Kassa — cheklar yig'indisi (1950 + 2600 = 4 550); zp — $ da. «Проёб»dagi cheklar, jarima, bonus, avanslar.
  - **Hisobotni botning o'ziga yozish mumkin:** tepasida ism bilan, masalan `Baxa` / `rd 19.10` / `1950` / `2600`.
    Ism notanish bo'lsa — «➕ Yangi xodim: Baxa» tugmasi chiqadi (shunday tanishtirasiz). Jarima ham:
    `@ivan штраф 5`. Guruhda ham xuddi shunday.
  - Bosh menyuda — 💰 **Cash**: dushanbadan beri jami kassa ($, faqat egaga) va «Задержки сейчас» — har RD
    da hozir nechta zaderjka (🟢 yo'q · 🟡 bor · 🔴 ko'p). Menyu o‘z joyida har 2 soniyada yangilanadi.
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
  - Pul amallari (to'landi, avans, ulushlar, foizlar) — faqat siz. Adminlar cheklarni tuzatadi.
  - Xodim faqat o'z zp sini ko'radi, so'rov avval sizga keladi. Daromadingizni faqat siz ko'rasiz.
- **📣 Push.** Har papka o'z akkauntidan, faqat qo'lda (🚀). Kimga va qaysi tartibda — soatga qarab:
  🌅 ertalab (13:00 gacha) — bugun gaplashmaganlar, kechagidan boshlab eskiroqlariga;
  ☀️ kunduzi — faqat bugun gaplashganlar: ertalabkilar → jim turganlar (30/60 daq) → hozirgina yozishganlar;
  🌙 kechqurun (19:00 dan) — avval bugungilar, keyin kechagi va eskiroqlar.
  Baza — 28.08.2026 dan keyin o'zi yozgan har bir lid (yangi kelgani ham, eskisi ham). Bot ularni bir marta to'liq
  tekshiradi (tugagach xabar keladi; qayta: 📣 Push → ⚙️ → 🔍 Bazani tekshirish). Vaqtlar va sana: 📣 Push → ⚙️.
  Papkaga akkaunt: 📣 Push → 📁 Papkalar → papka → 📲 Akkaunt (➕ yangisini shu yerning o'zida ulash mumkin).
- **📊 Hisobotlar.** Faqat buyruq bilan: shaxsiy chatda `/hisobot`, guruhda `/statistika` (🥇🥈🥉 bilan).
- **📈 Tahlil** (📊 Hisobotlar → 📈). Hammasi faqat vaqt va kim yozgani bo'yicha — matn o'qilmaydi:
  - 🕐 Soatlar — har soatda nechta lid yozdi va nechtasi zaderjkaga tushdi (bugun / 7 kun, RD bo'yicha).
  - 💤 Qotib qolgan — N kun (3) hech kim yozmagan lidlar; 📉 Soviyotgan — mijoz odatdagidan 3 barobar uzoq jim.
    Soviyotganlarni bot «Проёб»da o'zi eslatadi (har RD alohida, xodim belgilanadi).
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
