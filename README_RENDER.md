# XCODE Key Panel — Render / Termux

## Render ayarları

1. GitHub repo'ya bu klasörün içeriğini at (kökte api.py, bot.py olsun).
2. New Web Service → repo seç.
3. **Build Command:**
   ```
   pip install -r requirements.txt
   ```
4. **Start Command (sadece bot — Telegram cevap versin):**
   ```
   python bot.py
   ```
   veya bot + API birlikte:
   ```
   bash start.sh
   ```
5. **Environment:**
   - Name: `BOT_TOKEN`  Value: BotFather token
   - Name: `ADMIN_IDS`  Value: `7675625386`
6. Deploy.

Önemli: Start Command `gunicorn app:app` OLMAYACAK.
Doğru API: `gunicorn api:app`
Doğru bot: `python bot.py`

## Render free notu
Free plan ~15 dk işlem yoksa uyur. Uyurken bot mesaj cevaplamayabilir.
24/7 için Kerit / Inject / ücretli plan daha iyi.

## Termux
```
pkg install python -y
pip install -r requirements.txt
python bot.py
```

## Test
Telegram: /start
API (start.sh ile): GET /health
