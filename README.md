# مدیریت دعوت همکاران در بله — فاز ۲

فاز ۲ فقط **بررسی حساب بله** (`CHECK_BALE_ACCOUNT`) را اجرا می‌کند.

در این فاز **هیچ پیام خصوصی، دعوت به گروه، یا عملیات انبوه نوشتنی روی بله انجام نمی‌شود.**

## محدودیت مهم API بازو

API رسمی بازوی بله (`tapi.bale.ai`) کاربر را با **شماره موبایل** پیدا نمی‌کند؛ برای `getChat` به `user_id` نیاز دارد.

اگر در فایل Excel ستون `bale_user_id` / `user_id` داشته باشید، سیستم می‌تواند حساب را چک کند.

اگر فقط `name` و `phone` دارید، وضعیت همان `UNKNOWN` می‌ماند تا وقتی که:

- کاربر بازو را استارت کند و مخاطبش را Share کند، بعد `sync-bot-updates` را بزنید، یا
- در فاز بعد از لینک دعوت گروه استفاده شود (بدون پیام خصوصی از طرف ما).

## کارهایی که برای سرور موقت لازم است

ربات موقتی و رایگان است؛ **VPS، PostgreSQL، Redis، Docker و سرویس پولی لازم نیست.**

روی همین ویندوز:

1. Python 3.11+ را نصب کنید (اگر ندارید).
2. داخل بله `@BotFather` را باز کنید، `/newbot` بزنید، یک بازوی موقت بسازید و **توکن را فقط در فایل `.env` محلی** بگذارید. توکن را در چت یا Git نگذارید.
3. دیتابیس همان فایل رایگان `data/bale.db` است. سرور دیتابیس جدا نمی‌خواهد.
4. برای فاز ۲ لازم نیست بازو را ادمین گروه کنید. آن کار برای فاز دعوت است.
5. پروژه را روی همین سیستم اجرا کنید؛ نیازی به هاست ابری نیست.

## نصب

در PowerShell، داخل پوشه پروژه:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python -m bale_inviter init-db
```

سپس توکن بازو را در `.env` روی `BALE_BOT_TOKEN` بگذارید.

## استفاده

فایل Excel/CSV را در پوشه `imports/` بگذارید (این پوشه در Git نیست).

ستون‌های قابل تشخیص: `name` / `نام` و `phone` / `شماره`. ستون اختیاری: `bale_user_id` / `user_id`.

```powershell
python -m bale_inviter import-contacts .\imports\contacts.xlsx
python -m bale_inviter ping-bale
python -m bale_inviter enqueue-account-checks
python -m bale_inviter worker
python -m bale_inviter report
python -m bale_inviter serve
```

اگر همکاران بازو را باز کنند و مخاطب خود را برایش بفرستند:

```powershell
python -m bale_inviter sync-bot-updates
```

گزارش HTTP: [http://127.0.0.1:8000/report](http://127.0.0.1:8000/report)

`worker` را با `Ctrl+C` متوقف کنید. فاصله بین هر چک از `INVITE_INTERVAL` خوانده می‌شود.

## تست

```powershell
pytest
```

## وضعیت‌های مخاطب

- `bale_account_status`: `UNKNOWN` | `HAS_ACCOUNT` | `NO_ACCOUNT` | `ERROR`
- `direct_invite_status`: `NOT_STARTED` | `SUCCESS` | `FAILED` | `SKIPPED`
- `invite_link_status`: `NOT_SENT` | `SENT` | `FAILED`
- `join_status`: `UNKNOWN` | `JOINED` | `NOT_JOINED`

Job فعال فاز ۲: `CHECK_BALE_ACCOUNT`.

هنوز اجرا نمی‌شوند: `DIRECT_INVITE`, `SEND_INVITE_LINK`, `CHECK_JOIN_STATUS`.

## امنیت

- `.env` و فایل‌های Excel/CSV در Git نیستند.
- شماره موبایل در لاگ Mask می‌شود.
- توکن بازو هرگز نباید در Repository یا خروجی چت قرار بگیرد.
- Adapter فاز ۲ فقط `getMe` / `getChat` / `getUpdates` را صدا می‌زند.
