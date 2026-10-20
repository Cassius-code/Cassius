FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data \
    TZ_NAME=Asia/Tashkent

# PDF hisobot va panel rasmlari uchun zaxira shrift (kirill va lotin harflari)
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Hamma fayllar repozitoriyning ildizida (iPhone'dan yuklash oson) — konteyner ichida «app» paketi bo'ladi.
# Shriftlar (*.otf, *.ttf) — panel rasmlari uchun; yuklanmagan bo'lsa ham bot ishlaydi (oddiy shrift bilan).
COPY . /tmp/src
RUN mkdir -p app/fonts && cp /tmp/src/*.py app/ \
    && (cp /tmp/src/*.otf app/fonts/ 2>/dev/null || true) && (cp /tmp/src/*.ttf app/fonts/ 2>/dev/null || true) \
    && rm -rf /tmp/src \
    && cd app && rm -f breaks.py broadcast.py features.py i18n.py i18n_uz.py monitor.py screens.py sender.py \
    statuses.py worktime.py

RUN mkdir -p /data
CMD ["python", "-m", "app"]
