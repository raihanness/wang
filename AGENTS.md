# Wang — AGENTS.md

> Money tracker (Money+ cute style). Django 5 + MariaDB-ready for DOM Cloud, developed locally with SQLite until deploy. **Mobile-first UI**: bottom navbar, add-transaction bottom sheet, 480px phone frame. So the AI doesn't have to re-read everything.

## Quick start
```powershell
.\venv\Scripts\python manage.py runserver
# http://127.0.0.1:8000 — login demo / demo12345 (or Sign up)
```

## Stack & env
- **Python** `venv` at `./venv` — always use `.\venv\Scripts\python` / `.\venv\Scripts\pip`
- **Django** 5.2, **python-dotenv**, **Pillow**, **whitenoise**, **gunicorn**
- **DB**: `DB_ENGINE=sqlite` locally (default); `DB_ENGINE=mariadb` (or `mysql`) on DOM Cloud via env. See `.env.example`.
- **Settings** `config/settings.py` reads `.env`; `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` from env, `TIME_ZONE=Asia/Jakarta`, `whitenoise` for static, `STATIC_ROOT=staticfiles`.
- **Secrets**: `.env` is gitignored. Copy `.env.example` for DOM Cloud. `requirements.txt` uses `mysqlclient` off-Windows, `PyMySQL` on Windows; lock snapshot in `requirements.lock.txt` if present.

## Project layout
```
config/                Django project (settings, urls, wsgi)
tracker/               Main app
  models.py            Wallet, Category, Transaction
  views.py             dashboard, wallets, categories, transactions + auth
  forms.py             WalletForm, CategoryForm, TransactionForm
  urls.py + auth_urls  App routes + signup
  admin.py             Admin for all models
  migrations/          0001_initial, 0002 icon->material names
templates/
  base.html            480px phone frame, appbar, BOTTOM NAV with center + FAB
  tracker/
    _add_sheet.html    ADD-TRANSACTION BOTTOM SHEET (Expense/Income/Transfer tabs,
                      3-col category grid, From/To wallet selects, amount tap-to-edit)
    dashboard.html     balance card, wallet strip, recent list, 2 Chart.js charts
    wallet_*, category_*, transaction_*, confirm_delete
  registration/        login.html, signup.html
static/css/wang.css    Mobile-first pastel theme (Plus Jakarta Sans, Material Symbols)
manage.py
.env / .env.example / .gitignore / requirements.txt
```

## Mobile UI conventions (IMPORTANT)
- **Phone frame**: `.phone` caps every page at 480px, centered on desktop; body bg is a neutral tone. It is the ONLY mobile view — intended for phone use.
- **Bottom nav** (`.bottomnav`, fixed): Home, Wallets, center **+ FAB** (opens add sheet), History, Categories. Icons = Material Symbols.
- **Add sheet** (`_add_sheet.html`, included in `base.html` on EVERY page): Money+ style — header with ✕ / Expenses·Income·Transfer tabs / ✓ save. Category tabs show a 4-column grid (Money+ layout), transfer shows From→To wallet blocks + swap. A **Select Account** picker sheet (icon, name, balance, checkmark) picks the wallet for income/expense and the from/to wallets for transfer. Amount typed on a custom numeric **keypad** (digits, ., backspace); the **TODAY** key opens a CUSTOM date+time bottom sheet (`#date-sheet`: calendar grid + hour/min spinners, styled like the wallet picker). Sheet is fixed-height flex (min 78vh, max 92vh); the keypad + save buttons sit in a pinned bottom block (`.sheet-bottom`, z-index above content) while the category area scrolls behind it (`.sheet-scroll` overflow-y auto + spacer). Posts to `transaction_create` with hidden `kind/amount/date/note` + dynamic `category`/`wallet` or `from_wallet`/`to_wallet`. JS blocks submit without amount, category, wallet, or with same from/to.
- **Transaction.date is a DateTimeField** (migration 0003): `date` hidden input stores `YYYY-MM-DDTHH:MM` local; form parses via `DATETIME_INPUT_FORMATS` in settings + `DateTimeInput` widget. Dashboard/charts use `_month_bounds` datetimes; lists render `|date:"M j, Y · H:i"`.
- Every view must include `_sheet_context(request.user)` (expense_cats, income_cats, wallets) or the sheet breaks. Note: dashboard merges via `ctx.update()` — do NOT rebuild `ctx` from scratch or the sheet loses its data.
- **Icons**: Material Symbols Rounded (ligature names like `restaurant`, `payments`), NOT emoji. Wallet/Category `icon` field stores these names.
- **Font**: Plus Jakarta Sans (Google Fonts). Chart.js via CDN, uses `months_json`/`expense_cat_json` (`json_script`).
- Money shown with `intcomma`, no decimals (Rp, IDR app).

## Domain model
- **Wallet** `user, name (unique per user), type(cash/bank/ewallet/savings/other), icon, color, initial_balance, archived`. `current_balance` = initial + income − expense − out_transfers + in_transfers.
- **Category** `user, name, kind(income/expense), icon, color`. Unique on `(user, name, kind)`. Defaults seeded on first dashboard hit: 18 expense (Food, Daily, Transport, Social, Housing, Gifts, Communications, Utangs, Forgotten, Work/Projects, Electronics, Laptop Stuff, Clothing, Entertainment, Tax, Medical, Education, Misc) + 8 income (Mom, Dad, Sis, Housing, Utangs, Salary, Part-time, Bonus).
- **Transaction** `user, kind(income/expense/transfer), wallet, category, from_wallet/to_wallet, amount, note, date (DateTimeField)`. Validation: transfer needs `from_wallet`+`to_wallet` (different, no category); income/expense needs `wallet`+`category` (category.kind must match).
- All querysets are **user-scoped** (`user=request.user`); `@login_required` everywhere. `LOGIN_URL=login`, `LOGIN_REDIRECT_URL=dashboard`.

## URLs
- `/` dashboard (6-month bar + category doughnut via Chart.js, totals, recent)
- `/wallets/` list, `/wallets/new/`, `/wallets/<pk>/edit/`, `/wallets/<pk>/toggle/` archive
- `/categories/`, `/categories/new/`, `/…/edit/`, `/…/delete/`
- `/transactions/` (filters: `q, kind, wallet, from, to`), `/transactions/new/`, `/…/edit/`, `/…/delete/`
- `accounts/login/`, `accounts/logout/`, `accounts/signup/`
- `admin/`

## What was built this pass
- Created `venv`, installed Django stack into it (no global pip).
- `django-admin startproject config .` + `startapp tracker`.
- Rewrote `config/settings.py` for dotenv + MariaDB/SQLite switch + whitenoise.
- Implemented models/forms/views/urls/admin, seeded default categories + cash wallet, cute UI (`wang.css`) + Chart.js.

## Mobile redesign pass
- Mobile-first: 480px `.phone` frame, sticky appbar, fixed bottom nav (Home/Wallets/+FAB/History/Categories).
- Add-transaction **bottom sheet** with Expense/Income/Transfer tabs, 3-col category grid, From→To wallet selects + swap, tap-to-edit amount.
- Fonts/theme: Plus Jakarta Sans + Material Symbols Rounded; emoji icons migrated to material names (`0002` migration + data remap).
- All views now merge `_sheet_context(request.user)`; demo user: demo/demo12345.

## DOM Cloud / MariaDB deploy notes
- Set env on DOM Cloud: `DB_ENGINE=mariadb`, `DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`.
- `requirements.txt` already handles `mysqlclient`/`PyMySQL`; `collectstatic` + `migrate` on deploy.

## Conventions
- Use Decimal for money; humanize `intcomma` in templates.
- Transfers are double-entry via `from_wallet`/`out_transfers` and `to_wallet`/`in_transfers`.
- Keep AGENTS.md updated when you add models/routes.
