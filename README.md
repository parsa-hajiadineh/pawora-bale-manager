# مدیریت دعوت همکاران در بله — فاز ۱

هستهٔ مدیریت مخاطبین، وضعیت‌ها و صف Job. در این فاز **هیچ پیام خصوصی، دعوت به گروه، یا عملیات انبوه روی بله انجام نمی‌شود.**

## معماری

| بخش | انتخاب فاز ۱ (رایگان / موقت) |
| --- | --- |
| زبان | Python 3.11+ |
| رابط | CLI (`typer`) + API گزارش (`FastAPI`) |
| دیتابیس | SQLite فایل محلی — بدون سرور |
| صف Job | جدول `jobs` داخل همان SQLite — بدون Redis/Celery |
| تنظیمات | متغیر محیطی / فایل `.env` |
| لاگ | فایل چرخشی + کنسول، با Mask شماره |

لایه‌ها جدا هستند: Import، Domain، Database، Queue، Bale Adapter (فقط Interface)، Services، Reporting، Config، Logging.

## کارهایی که برای سرور موقت لازم نیست

چون ربات موقتی و رایگان است:

- نیازی به PostgreSQL، Redis، Docker، یا VPS پولی نیست.
- دیتابیس همان فایل `data/bale.db` است.
- روی همین ویندوز (یا هر سیستم با Python) اجرا می‌شود.
- در فاز ۱ توکن بله لازم نیست و نباید در کد یا چت قرار بگیرد.

اگر بعداً خواستید روی یک سیستم دیگر اجرا کنید، فقط Python را نصب کنید، پروژه را کپی کنید و `.env` را آنجا بسازید.

## نصب

در PowerShell، داخل پوشه پروژه:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python -m bale_inviter init-db
```

## استفاده

فایل Excel/CSV را در پوشه `imports/` بگذارید (این پوشه در Git نیست).

ستون‌های قابل تشخیص: `name` / `نام` و `phone` / `شماره`.

```powershell
python -m bale_inviter import-contacts .\imports\contacts.xlsx
python -m bale_inviter report
python -m bale_inviter serve
```

گزارش HTTP: [http://127.0.0.1:8000/report](http://127.0.0.1:8000/report)

## تست

```powershell
pytest
```

## وضعیت‌های مخاطب

- `bale_account_status`: `UNKNOWN` | `HAS_ACCOUNT` | `NO_ACCOUNT` | `ERROR`
- `direct_invite_status`: `NOT_STARTED` | `SUCCESS` | `FAILED` | `SKIPPED`
- `invite_link_status`: `NOT_SENT` | `SENT` | `FAILED`
- `join_status`: `UNKNOWN` | `JOINED` | `NOT_JOINED`

Jobهای آینده فقط در صف ثبت می‌شوند و اجرا نمی‌گردند: `CHECK_BALE_ACCOUNT`, `DIRECT_INVITE`, `SEND_INVITE_LINK`, `CHECK_JOIN_STATUS`.

## امنیت

- `.env` و فایل‌های Excel/CSV در Git نیستند.
- شماره موبایل در لاگ Mask می‌شود.
- Adapter بله در فاز ۱ `NotImplementedError` می‌دهد و عمداً به API بله وصل نیست.
