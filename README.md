# دعوت همکاران به گروه تلگرام با شماره موبایل

ربات تلگرام هم مثل بله نمی‌تواند با شماره پیام بدهد. این برنامه با **حساب کاربری تلگرام خودت** کار می‌کند (مثل اپ رسمی): شماره را چک می‌کند، اگر اکانت داشت به گروه دعوت می‌کند. دانه‌دانه دستی لازم نیست.

`INVITE_INTERVAL=20` یعنی حدود ۲۰ ثانیه فاصله بین هر نفر؛ برای ۶۰۰ نفر چند ساعت طول می‌کشد تا تلگرام حساب را محدود نکند.

## کار رایگان که باید انجام بدهی

1. از [my.telegram.org](https://my.telegram.org) یک App رایگان بساز و `api_id` / `api_hash` را فقط در `.env` بگذار.
2. حساب تلگرامی که **ادمین گروه هدف** است را برای ورود استفاده کن.
3. `GROUP_ID` را بگذار: `@username` گروه یا شناسه عددی مثل `-100123...`.
4. فایل Excel را Import کن و یک‌بار `telegram-login` را در PowerShell بزن.

توکن و api_hash را در چت یا Git نگذار. فایل `data/telegram.session` هم در Git نیست.

## نصب و اجرا

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
python -m bale_inviter init-db
python -m bale_inviter telegram-login
python -m bale_inviter import-contacts .\imports\contacts.xlsx
python -m bale_inviter ping-bale
python -m bale_inviter prepare-group
python -m bale_inviter run-invites
python -m bale_inviter report
```

`run-invites` اول همه شماره‌ها را چک می‌کند، بعد کسانی که تلگرام دارند را به گروه دعوت می‌کند. اگر دعوت مستقیم گیر کند، لینک گروه را پیام می‌دهد. بعد عضویت را هم چک می‌کند.

`plan` بدون لاگین می‌گوید چه کاری در صف می‌رود. `--dry-run` دعوت و پیام خصوصی نمی‌فرستد. `export-report` یک CSV محلی از وضعیت‌ها می‌سازد.

توقف: `Ctrl+C`. بعداً دوباره `run-invites` را بزن؛ تکراری‌ها را صف رد می‌کند.

## محدودیت‌ها

- کسی که تلگرام ندارد دعوت نمی‌شود.
- بعضی اکانت‌ها حریم خصوصی دارند و به گروه اضافه نمی‌شوند؛ برای آن‌ها لینک فرستاده می‌شود.
- دعوت انبوه ممکن است Flood Wait بگیرد؛ فاصله را کم نکن.
- این کار با ربات BotFather انجام نمی‌شود؛ باید همان حساب ادمین گروه لاگین شود.

## تست

```powershell
pytest
```
