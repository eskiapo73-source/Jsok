import os
import sqlite3
import secrets
import string
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes
)

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "keys.db")
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            key TEXT PRIMARY KEY,
            created TEXT NOT NULL,
            expires TEXT,
            max_devices INTEGER NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            key TEXT NOT NULL,
            device_id TEXT NOT NULL,
            banned INTEGER NOT NULL DEFAULT 0,
            first_seen TEXT NOT NULL,
            PRIMARY KEY(key, device_id)
        )
    """)
    con.commit()
    return con


def now():
    return datetime.now(timezone.utc)


def parse_date(value):
    return datetime.fromisoformat(value) if value else None


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id if update.effective_user else 0
        if not ADMIN_IDS or uid not in ADMIN_IDS:
            await update.effective_message.reply_text(
                "⛔ Yetkin yok. Bot yöneticisi tarafından izin verilmelidir."
            )
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


def make_key():
    alphabet = string.ascii_uppercase + string.digits
    return "PAPK-" + "".join(secrets.choice(alphabet) for _ in range(16))


@admin_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🔐 KEY PANEL\n\n"
        "/key_olustur <gün> <cihaz>\n"
        "Örnek: /key_olustur 30 1\n"
        "Sınırsız süre: /key_olustur 0 1\n\n"
        "/key_liste\n"
        "/key_bilgi KEY\n"
        "/key_kapat KEY\n"
        "/key_ac KEY\n"
        "/cihazlar KEY\n"
        "/cihaz_engelle KEY DEVICE_ID\n"
        "/cihaz_ac KEY DEVICE_ID\n"
        "/yardim"
    )


@admin_only
async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


@admin_only
async def key_olustur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2:
        await update.effective_message.reply_text(
            "Kullanım: /key_olustur <gün> <cihaz>\nÖrnek: /key_olustur 30 1"
        )
        return
    try:
        days, devices = map(int, context.args)
        if days < 0 or not 1 <= devices <= 100:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(
            "Gün 0 veya daha büyük; cihaz sayısı 1-100 olmalı."
        )
        return

    con = connect()
    key = make_key()
    while con.execute("SELECT 1 FROM licenses WHERE key=?", (key,)).fetchone():
        key = make_key()

    created = now()
    expires = (created + timedelta(days=days)).isoformat() if days else None
    con.execute(
        "INSERT INTO licenses(key,created,expires,max_devices) VALUES(?,?,?,?)",
        (key, created.isoformat(), expires, devices)
    )
    con.commit()
    con.close()

    await update.effective_message.reply_text(
        f"✅ KEY OLUŞTURULDU\n\n"
        f"🔑 Key: `{key}`\n"
        f"⏳ Süre: {'Sınırsız' if days == 0 else str(days) + ' gün'}\n"
        f"📱 Cihaz limiti: {devices}",
        parse_mode="Markdown"
    )


@admin_only
async def key_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    con = connect()
    rows = con.execute(
        "SELECT * FROM licenses ORDER BY created DESC LIMIT 50"
    ).fetchall()
    con.close()
    if not rows:
        await update.effective_message.reply_text("Henüz key oluşturulmamış.")
        return

    lines = ["🔑 KEY LİSTESİ (son 50)"]
    for r in rows:
        exp = parse_date(r["expires"])
        expired = exp is not None and now() >= exp
        status = "Kapalı" if not r["active"] else ("Süresi dolmuş" if expired else "Aktif")
        lines.append(
            f"\n{r['key']}\nDurum: {status}\nCihaz limiti: {r['max_devices']}"
        )
    await update.effective_message.reply_text("\n".join(lines))


@admin_only
async def key_bilgi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.effective_message.reply_text("Kullanım: /key_bilgi KEY")
        return
    con = connect()
    r = con.execute(
        "SELECT * FROM licenses WHERE key=?", (context.args[0].upper(),)
    ).fetchone()
    count = con.execute(
        "SELECT COUNT(*) FROM devices WHERE key=? AND banned=0",
        (context.args[0].upper(),)
    ).fetchone()[0]
    banned = con.execute(
        "SELECT COUNT(*) FROM devices WHERE key=? AND banned=1",
        (context.args[0].upper(),)
    ).fetchone()[0]
    con.close()
    if not r:
        await update.effective_message.reply_text("❌ Key bulunamadı.")
        return
    exp = parse_date(r["expires"])
    await update.effective_message.reply_text(
        f"🔑 {r['key']}\n"
        f"Durum: {'Aktif' if r['active'] else 'Kapalı'}\n"
        f"Oluşturulma: {r['created']}\n"
        f"Bitiş: {exp.isoformat() if exp else 'Sınırsız'}\n"
        f"Cihaz limiti: {r['max_devices']}\n"
        f"Kayıtlı cihaz: {count}\nEngelli cihaz: {banned}"
    )


async def change_active(update, context, active):
    if len(context.args) != 1:
        await update.effective_message.reply_text("Kullanım: /key_kapat KEY")
        return
    key = context.args[0].upper()
    con = connect()
    cur = con.execute(
        "UPDATE licenses SET active=? WHERE key=?", (active, key)
    )
    con.commit()
    con.close()
    await update.effective_message.reply_text(
        "✅ İşlem tamamlandı." if cur.rowcount else "❌ Key bulunamadı."
    )


@admin_only
async def key_kapat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_active(update, context, 0)


@admin_only
async def key_ac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_active(update, context, 1)


@admin_only
async def cihazlar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.effective_message.reply_text("Kullanım: /cihazlar KEY")
        return
    con = connect()
    rows = con.execute(
        "SELECT device_id,banned FROM devices WHERE key=?",
        (context.args[0].upper(),)
    ).fetchall()
    con.close()
    if not rows:
        await update.effective_message.reply_text(
            "Bu key için kayıtlı cihaz yok. APK henüz API'ye bağlanmadıysa bu normal."
        )
        return
    lines = ["📱 CİHAZLAR"]
    for r in rows:
        lines.append(
            f"{r['device_id']} — {'🚫 Engelli' if r['banned'] else '✅ Aktif'}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def change_device_ban(update, context, banned):
    if len(context.args) != 2:
        await update.effective_message.reply_text(
            "Kullanım: /cihaz_engelle KEY DEVICE_ID"
        )
        return
    key, device_id = context.args[0].upper(), context.args[1]
    con = connect()
    exists = con.execute(
        "SELECT 1 FROM devices WHERE key=? AND device_id=?",
        (key, device_id)
    ).fetchone()
    if not exists:
        con.close()
        await update.effective_message.reply_text(
            "❌ Cihaz bulunamadı. Önce APK'nın API'ye bağlanması gerekir."
        )
        return
    con.execute(
        "UPDATE devices SET banned=? WHERE key=? AND device_id=?",
        (banned, key, device_id)
    )
    con.commit()
    con.close()
    await update.effective_message.reply_text(
        "🚫 Cihaz engellendi." if banned else "✅ Cihaz engeli kaldırıldı."
    )


@admin_only
async def cihaz_engelle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_device_ban(update, context, 1)


@admin_only
async def cihaz_ac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_device_ban(update, context, 0)


def main():
    if not TOKEN:
        raise SystemExit(
            "BOT_TOKEN ayarlı değil. Önce export BOT_TOKEN='YENİ_TOKEN' çalıştır."
        )
    connect()
    app = Application.builder().token(TOKEN).build()
    for name, func in [
        ("start", start),
        ("yardim", yardim),
        ("key_olustur", key_olustur),
        ("key_liste", key_liste),
        ("key_bilgi", key_bilgi),
        ("key_kapat", key_kapat),
        ("key_ac", key_ac),
        ("cihazlar", cihazlar),
        ("cihaz_engelle", cihaz_engelle),
        ("cihaz_ac", cihaz_ac),
    ]:
        app.add_handler(CommandHandler(name, func))
    print("KEY PANEL çalışıyor. Durdurmak için CTRL+C.")
    app.run_polling()


if __name__ == "__main__":
    main()