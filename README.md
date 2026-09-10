# مدیریت دعوت همکاران در بله — فاز ۳

بازوی موقت می‌تواند مخاطب را **مستقیم به گروه اضافه کند** یا **لینک عضویت را در پیام خصوصی بفرستد**.

API رسمی بازو کاربر را با شماره موبایل پیدا نمی‌کند. برای دعوت مستقیم یا پیام خصوصی باید `user_id` معلوم باشد: از ستون اختیاری Excel، یا وقتی همکار بازو را Start کند / شماره‌اش را Share کند.

## کار رایگان روی سیستم خودتان

VPS، PostgreSQL، Redis و سرویس پولی لازم نیست. دیتابیس فایل `data/bale.db` است.

1. داخل بله `@BotFather` → `/newbot` → توکن را فقط در `.env` بگذارید.
2. بازو را به گروه هدف اضافه کنید و **ادمین با دسترسی دعوت اعضا** کنید.
3. یک پیام در گروه بفرستید، بعد `run-bot` را اجرا کنید تا `chat_id` گروه در لاگ دیده شود و همان را در `GROUP_ID` بگذارید.
4. یا لینک عضویت گروه را دستی در `INVITE_LINK` بگذارید.

توکن را در چت یا Git نگذارید.

## نصب

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python -m bale_inviter init-db
```

## اجرا

فایل Excel/CSV را در `imports/` بگذارید.

```powershell
python -m bale_inviter import-contacts .\imports\contacts.xlsx
python -m bale_inviter ping-bale
python -m bale_inviter prepare-group
python -m bale_inviter enqueue-invites
python -m bale_inviter run-bot
python -m bale_inviter report
```

`run-bot` همزمان:

- به `/start` جواب می‌دهد و لینک گروه را می‌فرستد
- اگر مخاطب شماره را Share کند، با فایل Excel مچ می‌شود و دعوت می‌کند
- Jobهای صف را با فاصله `INVITE_INTERVAL` اجرا می‌کند

`INVITE_STRATEGY=auto` یعنی اول دعوت مستقیم؛ اگر شکست بخورد لینک خصوصی ارسال می‌شود.

`Ctrl+C` برای توقف.

گزارش HTTP: [http://127.0.0.1:8000/report](http://127.0.0.1:8000/report)

## تست

```powershell
pytest
```

## محدودیت Bot API

بدون `bale_user_id` نمی‌توان ۶۰۰ نفر را فقط با شماره، مستقیم عضو کرد. مسیر عملی برای لیست همکاران:

- لینک بازو را برایشان بفرستید تا Start کنند، یا
- ستون `user_id` را اگر دارید وارد کنید، یا
- لینک گروه را بیرون از بله پخش کنید.
