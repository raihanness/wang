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
- **Secrets**: `.env` is gitignored. Copy `.env.example` for DOM Cloud. `requirements.txt` uses `PyMySQL` across all platforms (registered via `config/__init__.py`).

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
    dashboard.html     HOME — balance card, wallet strip, date-grouped history (search + day totals)
    graphs.html        GRAPHS — month nav, Expenses/Income tabs, pie + 6-month bar (Chart.js)
    wallet_*, category_*, transaction_*, confirm_delete
  registration/        login.html, signup.html
static/
  css/wang.css         Mobile-first pastel theme (Plus Jakarta Sans, Material Symbols)
  js/app.js            SPA shell: Turbo page-swap (view transitions), appbar title,
                       sheet open/close, sheet binding. Loaded once in <head>.
manage.py
android/               Native Android Studio WebView project (Option 3 APK wrapper)
.env / .env.example / .gitignore / requirements.txt
```

## SPA navigation (Turbo — IMPORTANT)
- **Hotwired Turbo 8** CDN + `static/js/app.js` loaded in `<head>`. Internal links/filters/forms navigate via Turbo: only `<main>` content swaps, the shell (appbar/bottomnav/add-sheet) persists. `<meta name="turbo-cache-control" content="no-preview">` disables stale preview snapshots.
- **Page-swap animation**: do NOT use `document.startViewTransition` — it froze Turbo renders on some browsers. Instead `app.js` adds `.turbo-enter` to `<main>` on every `turbo:render` and CSS animates `page-in` (fade + slide-up), disabled for reduced-motion.
- **Appbar title** stays consistently as "Wang" brand title across all pages.
- **Inline scripts gotcha**: Turbo re-runs page `<script>`s after each visit. Chart/graph scripts must guard via `turbo:load` + destroy stale `Chart.instances`. `_add_sheet.html` binds only once (checks `document.body.wangSheetBound`) and only seeds hour/min spinner options when empty.
- Turbo follows POST redirects; transaction add/edit/delete redirect to `dashboard`. Forms inside sheets post via normal POST; Turbo handles it and swaps in the result + messages.
- Sheet markup lives in `.sheet-root` so it survives page swaps (Turbo keeps it — matches by id).

## Mobile UI conventions (IMPORTANT)
- **Phone frame**: `.phone` caps every page at 480px, centered on desktop; body bg is a neutral tone. It is the ONLY mobile view — intended for phone use.
- **Bottom nav** (`.bottomnav`, fixed): Home, Wallets, center **+ FAB** (opens add sheet), History, Categories. Icons = Material Symbols.
- **Add sheet** (`_add_sheet.html`, included in `base.html` on EVERY page): Money+ style — header with ✕ / Expenses·Income·Transfer tabs / ✓ save. Category tabs show a 4-column grid (Money+ layout), transfer shows From→To wallet blocks + swap. A **Select Account** picker sheet (icon, name, balance, checkmark) picks the wallet for income/expense and the from/to wallets for transfer. **Spacious 2-tier input section**: Row 1 contains the wallet selector chip + generous note field with integrated camera attachment button & photo preview chip; Row 2 contains a dedicated hero amount bar (`Rp...`) with dynamic category name indicator. Amount typed on a custom numeric **keypad** (digits, ., backspace); the **TODAY** key opens a CUSTOM date+time bottom sheet (`#date-sheet`: calendar grid + hour/min spinners, styled like the wallet picker). Sheet is fixed-height flex (min 78vh, max 92vh); the keypad + save buttons sit in a pinned bottom block (`.sheet-bottom`, z-index above content) while the category area scrolls behind it (`.sheet-scroll` overflow-y auto + spacer). Posts to `transaction_create` with hidden `kind/amount/date/note` + dynamic `category`/`wallet` or `from_wallet`/`to_wallet`. JS blocks submit without amount, category, wallet, or with same from/to.
- **Transaction.date is a DateTimeField** (migration 0003): `date` hidden input stores `YYYY-MM-DDTHH:MM` local; form parses via `DATETIME_INPUT_FORMATS` in settings + `DateTimeInput` widget. Dashboard/charts use `_month_bounds` datetimes; lists render `|date:"M j, Y · H:i"`.
- Every view must include `_sheet_context(request.user)` (expense_cats, income_cats, wallets) or the sheet breaks. Note: dashboard merges via `ctx.update()` — do NOT rebuild `ctx` from scratch or the sheet loses its data.
- **Icons**: Material Symbols Rounded (ligature names like `restaurant`, `payments`), NOT emoji. Wallet/Category `icon` field stores these names.
- **Font**: Plus Jakarta Sans (Google Fonts). Chart.js via CDN, uses `months_json`/`expense_cat_json` (`json_script`).
- Money shown with `intcomma`, no decimals (Rp, IDR app).

## Domain model
- **Wallet** `user, name (unique per user), type(cash/bank/ewallet/savings/other), icon, color, initial_balance, archived, include_in_total, order`. `current_balance` = initial + income − expense − out_transfers + in_transfers. Total balance aggregates wallets where `include_in_total=True` and `archived=False`. Custom user ordering via `order`.
- **Category** `user, name, kind(income/expense), icon, color`. Unique on `(user, name, kind)`. Defaults seeded on first dashboard hit: 18 expense + 8 income.
- **Transaction** `user, kind(income/expense/transfer), wallet, category, from_wallet/to_wallet, amount, note, image (ImageField), date (DateTimeField)`. Validation: transfer needs `from_wallet`+`to_wallet` (different, no category); income/expense needs `wallet`+`category` (category.kind must match). **Receipt Optimization & Lifecycle**: Uploaded photos are automatically converted to optimized WebP format and resized to max 1200px (LANCZOS, EXIF orientation corrected). When a transaction is edited and its receipt is replaced or removed, or when a transaction is deleted, the old file on disk is automatically deleted to prevent orphaned storage.
- **Subscription** `user, name, amount, wallet, category, cycle(monthly/yearly/weekly), due_month (1-12, for yearly), due_day (1-31), icon, color, active, last_paid_date, created_at`. Properties: `is_paid_this_cycle`, `next_due_date`, `days_until_due`, `status_badge` (Paid ✓, Due today, Due in X days, Overdue).
- **Budget** `user, category (nullable for overall daily), amount, created_at, updated_at`.
- All querysets are **user-scoped** (`user=request.user`); `@login_required` everywhere. `LOGIN_URL=login`, `LOGIN_REDIRECT_URL=dashboard`.

## URLs
- `/` **Home** — balance card + daily budget card with real-time spend pace + recurring subscriptions carousel + date-grouped history (search `?q=`, day totals, newest first, quick filter chips)
- `/graphs/` **Graphs** — `?month=YYYY-MM` + `?kind=expense|income`; 3-metric insight strip (Daily Avg, Month-End Projected Spend, Peak Spending Day) + animated category breakdown percentage bars + 6-month trend bar
- `/budgets/set/` (POST — set or remove daily budget amount)
- `/export/csv/` (`?month=YYYY-MM` or `?all=1` — 1-tap Excel UTF-8 BOM CSV export)
- `/subscriptions/` list, `/subscriptions/new/`, `/subscriptions/<pk>/edit/`, `/subscriptions/<pk>/delete/`, `/subscriptions/<pk>/pay/` (1-tap expense logging)
- `/wallets/` 2x2 grid list + manual reordering (`/wallets/reorder/`), `/wallets/new/`, `/wallets/<pk>/edit/`, `/wallets/<pk>/delete/`, `/wallets/<pk>/toggle/` archive, `/wallets/<pk>/toggle-total/` toggle total balance inclusion
- `/categories/`, `/categories/new/`, `/…/edit/`, `/…/delete/` + Recurring Payments banner + 1-Tap CSV Data Export banner
- `/transactions/` (legacy/internal, filters: `q, kind, wallet, from, to`), `/transactions/new/`, `/…/edit/`, `/…/delete/`
- `accounts/login/`, `accounts/logout/`, `accounts/signup/` (disabled; redirects to login)
- `admin/`

- **Daily Budgets with Real-Time Spending Pace**: Added `Budget` model, `/budgets/set/` endpoint, and smooth animated `#budget-sheet` bottom sheet with quick daily presets (50K, 100K, 150K, 200K, 300K, 500K). The dashboard daily budget card features an ultra-compact 2-tier card layout with dynamic tri-color progress bars (emerald <60%, amber 60–84%, coral ≥85% or over), remaining daily allowance (`Rp... left`) or overspend alert (`Over by Rp...`), today's total spend against the daily target, and a compact Material Symbols status icon indicator (`check_circle` for under budget, `warning` for pacing well, `error` for almost at limit, `cancel` for over limit).
- **Search Bar Single-Line Pill Layout**: Polished `.search-form` into a unified, responsive flex pill (`border-radius: 999px`) with centered search icon, inline non-wrapping input field, subtle border/shadow tokens, clear button (`✕`), and peach focus ring.
- **Transaction Detail Bottom Sheet (`_detail_sheet.html`)**: Native-feel inspection modal invoked by tapping any transaction row (`.js-detail-tx`), featuring buttery-smooth CSS bottom-slide and backdrop fade animations matching the add-transaction sheet. Displays category hero badge, formatted amount, kind tag, timestamp, wallet attribution, note bubble, interactive receipt photo thumbnail (linked to full-screen lightbox), and 1-tap Edit and Delete action buttons.
- **1-Tap CSV Data Export on Categories Page (`/export/csv/`)**: Instant data export banner placed on `/categories/` right below the Recurring Payments card. Emits Microsoft Excel-friendly UTF-8 BOM (`\ufeff`) CSV files with Date, Time, Type, Category, Account, From Account, To Account, Amount (IDR), Note, and Receipt URL.
- **Paid-Aware Subscription Cycle Progression**: When paying a subscription via 1-tap check (✓), `last_paid_date` is updated to current date, marking the current billing cycle as `Paid ✓` with emerald badges, disabling the payment button to prevent duplicate payments, and immediately rolling over `next_due_date` to the subsequent cycle. Also provides real-time `Overdue` alerts if an unpaid subscription passes its due date.
- **Compact Total Balance & Today Hero Card on Home**: Upgraded the top hero card on `/` to present a single compact top row displaying `Total Balance` with an interactive privacy eye toggle (`visibility` / `visibility_off`) on the left and the right-aligned consolidated net balance (`Rp...` / `Rp ••••••`, with `localStorage` persistence and sound feedback), followed by a subtle divider and today's date, net badge, and income/expense breakdown boxes.
- **Smart Keypad: Inline Math Calculator**: Reorganized keypad in `_add_sheet.html` into a 4x4 standard calculator grid (`7 8 9 ÷`, `4 5 6 ×`, `1 2 3 −`, `. 0 ⌫ +`) with inline expression parsing, formatted expression hero display (e.g. `18,000 + 7,000`), real-time calculation preview badge (`= Rp25,000`), dynamic `=` key toggle, and automatic evaluation upon operator chaining or tapping `Save`.
- **Category Frequency Ordering in Bottom Sheet**: In `_sheet_context`, annotated categories with `tx_count = Count("transactions")` and ordered by `"-tx_count", "name"` so user's most frequently logged categories naturally appear at the top/start of the 4-column category grid.
- **Income vs. Expense Dual Cashflow Chart on `/graphs/`**: Upgraded 6-month spending chart to render a side-by-side grouped bar chart with emerald Income and coral Expense bars, net monthly cashflow tooltips (`+RpX (Y% saved)`), and a 3-metric average summary strip (Avg Income, Avg Spend, Avg Net/mo).
- **Annual Year-in-Review Summary on `/graphs/`**: Added top period switcher (`Monthly` vs `Annual Year`), year stepper (`< 2026 >`), Net Annual Savings hero card with % saved badge, 12-Month Dual Cashflow Bar Chart, Top 3 Biggest Expense Categories podium with Material Symbol medal badges (`workspace_premium` #1, #2, #3 with gold/silver/bronze tints) and % share, and Year Highlights (Best Savings Month, Peak Spend Month, Monthly Average Spend).
- **Dynamic Keypad Hiding During Note Editing in Bottom Sheet**: When the note input field (`#sheet-note`) is focused on mobile/desktop, the custom numeric keypad (`#keypad`) automatically collapses and hides (`.sheet.is-typing-note #keypad { display: none !important; }`), giving the native virtual keyboard and note suggestion chips ample vertical breathing room without crowding the viewport. Once the user taps "Done" (Enter, via `enterkeyhint="done"`), taps a suggestion chip, clicks the amount bar, taps outside, or closes the virtual keyboard, the numeric keypad smoothly reappears with a sleek rise micro-animation (`keypadPop`).
- **Smart Note Auto-Suggestions in Bottom Sheet**: As user types letters/words in the note field (`#sheet-note`), interactive pill suggestion chips (`.note-suggestion-chip`) filter and pop up in real time from the user's past unique notes. Tapping any chip fills the note instantly with haptic/audio tap feedback.
- **Interactive Month Picker Popover on Home**: Tapping the compact month navigator badge (`#c-month-trigger`, e.g. `Sep 2026 ▾`) opens a floating popover (`#month-popover`) featuring year stepping (`< 2026 >`), a 4x3 12-month jump grid with active/current-month indicator dots, and a "Current Month" button that preserves search query and filter chips while swapping via Turbo. Months with no transactions are muted, disabled, and unclickable (`.disabled`, `aria-disabled="true"`, `opacity: .2; pointer-events: none;`), while years without data are bounded (`#m-year-prev` / `#m-year-next` disable at `min_year` and `max_year`).
- **Subscriptions Carousel on Home**: Replaced the compact wallet carousel on `/` with a streamlined recurring subscriptions / bills carousel with dynamic countdown badges and 1-tap quick pay actions.
- **2x2 Wallets Grid on `/wallets/`**: Redesigned the wallets view from stacked single-column rows into an elegant 2-column grid format with balance displays, type badges, total balance inclusion eye toggles, and edit actions.
- **Daily Average Spending Insight & Spend Projection**: On `/graphs/`, a 3-metric insight banner displays real-time `Daily Avg` (/day), `Projected Total` (estimated month-end spend based on elapsed days), and `Peak Day` (highest spend date and amount).
- **Recurring Subscriptions & Bills Tracker**: Added `Subscription` model, full CRUD views, monthly commitment total card, countdown badges (`Due today`, `Due in X days`), and a 1-tap "Pay / Log Transaction" action.
- **Receipt & Note Photo Attachments**: Added `ImageField` on `Transaction`, camera/photo attachment button and instant preview thumbnail in the bottom sheet (`_add_sheet.html`), receipt badge indicator on transaction rows, and full-screen image lightbox viewer modal with backdrop click dismiss.
- **Light/Dark theme engine**: zero-flash pre-paint loader in `<head>`, `#theme-toggle` in appbar actions, `localStorage` persistence, warm charcoal & surface palette (`#11100f` base with radial ambient gradient glow, `--surface: #1e1e1d` cards, `--surface-2: #2e2b28`, `--surface-3: #36332f`), and automated Chart.js grid & axis color sync.
- **Login page UI overhaul**: ambient animated gradient glow (`.auth-ambient-glow`), floating glassmorphism card (`.auth-card`), leading icons (`person`, `lock`), and 1-tap interactive password reveal eye toggle (`visibility` / `visibility_off`).
- **Global form inputs polish**: unified token-based inputs across all forms with consistent border-radius (14px), surface tokens, and peach glow focus rings.
- **Turbo 8 SPA navigation**: only `<main>` swaps; shell persists; appbar title follows page via `data-page`; view-transition page fade/slide (reduced-motion aware); sheets close on render; add-sheet binds once.
- **Visual Icon & Color Swatch Picker Suite**: integrated in Wallet Form, Category Form, and Subscription Form (`_icon_color_picker.html`).
- **Animated Category Percentage Progress Bars**: On `/graphs/`, category breakdown rows show precise percentage badges and animated horizontal fill bars.
- **Quick Filter Chips on Home**: 1-tap filtering across `All`, `Expenses`, `Income`, and `Transfer` transactions within the `tx-history` Turbo frame.
- **Web Audio Synthesizer & Haptic Engine**: zero-dependency Web Audio API sound system with appbar `#sound-toggle` (`volume_up` / `volume_off`), synthesized tactile feedback (bubbles, clicks, chimes, knocks) and haptic vibration.
- **Zero-lag solid surfaces**: Replaced all `backdrop-filter: blur(...)` and ambient blur animations with 100% solid surface colors (`--appbar-bg: var(--bg)`, `--bottomnav-bg: var(--surface)` with clean border-top separation), eliminating GPU compositing overhead and scrolling lag on mobile devices.
- **In-Sheet Delete Confirmation Modal (`_confirm_sheet.html`)**: Replaced immediate unconfirmed POST deletions in the Detail Sheet and native browser `confirm(...)` popups in the Edit Sheet with a cohesive Wang-styled confirmation bottom sheet (`#confirm-sheet` with z-index: 110 above active sheets). Features a circular coral trash icon badge, "Delete Transaction?" title, context-aware description, transaction preview chip (e.g. `Food · Rp50,000`), and dual action buttons (`Cancel` and `Delete`). Dismisses smoothly upon cancel or backdrop click, returning the user to the underlying sheet, or submits via Turbo with `'delete'` synthesized audio/haptics. Also polished `confirm_delete.html` with matching icon badge and red `.btn.btn-delete` button.
- **Mobile Fast Navigation Suite**:
  - **Touchstart / Pointerdown Instant Preloading**: Added `pointerdown` listeners and `data-turbo-preload` to `.bottomnav .bn-item` links. The exact millisecond a user's finger touches down on the screen, Turbo begins downloading the target view 150–300ms before the `click` event fires, achieving desktop-like instantaneous page swaps on touchscreens.
  - **Add-Sheet DOM Preservation (`data-turbo-permanent`)**: Marked `#sheet-root-container` as `data-turbo-permanent` so Turbo persists the 54 KB bottom sheet across page swaps rather than tearing down and reconstructing thousands of DOM elements on every tab switch.
  - **Instant Turbo Progress Feedback**: Configured `Turbo.setProgressBarDelay(50)` (down from default 500ms) with a vibrant coral-to-emerald gradient progress bar (`.turbo-progress-bar`) providing instant visual feedback on slow connections.
  - **Eliminated N+1 Database Queries**: Implemented `_get_wallets_with_balances` using 3 bulk SQL aggregations for income, expense, and transfers, caching `_cached_balance` on wallet instances and slashing database queries from ~38 down to ~12–17 per view.
- **Offline Service Worker (`sw.js` PWA Caching)**: Root-scoped service worker registered at `/sw.js` (`Service-Worker-Allowed: /`) with intelligent multi-tier caching: Cache-First for immutable Google Fonts and Material Symbols woff2 files (`fonts.gstatic.com`), Stale-While-Revalidate for static assets (`wang.css`, `app.js`, manifest, app icons, Turbo 8, Chart.js), and Network-First for HTML navigation with automatic fallback to cached pages and a cute mobile-first `/offline/` screen. Also includes real-time online/offline connectivity indicator toast banners (`cloud_off` / `cloud_done`).
- **Unified Floating Toast Notification System**: Replaced static inline message blocks with floating pill toasts (`.toast-container` / `.toast-pill`) that slide down from the top with cubic-bezier spring physics, Material Symbols icons (`check_circle`, `error`, `warning`, `info`, `cloud_done`, `cloud_off`), sound feedback (`chime`, `knock`, `tap`), 1-tap manual dismiss, and automatic 3.2-second slide-up exit. Powered by `initToasts()` for Turbo renders and programmatic `showToast(msg, type, duration)` for client-side events.
- **Receipt Image Optimization & Storage Lifecycle**: Incoming receipt photos are resized (max 1200px) and converted into modern WebP format using Pillow (`optimize_receipt_image`), reducing storage footprints by up to 95%. When a transaction is deleted, its receipt image is automatically cleaned from disk via `delete()` and `post_delete` signals. When a transaction's receipt is replaced or removed in the edit bottom sheet (`#sheet-image-clear`), the old file on disk is safely unlinked to prevent orphaned files.
- **Multi-Filter Bottom Sheet (`_filter_sheet.html`)**: Native bottom sheet modal on `/` opened via the `#multi-filter-trigger` button in the dashboard filter row, with dynamic active count badge. Supports multi-dimensional filtering by transaction kind (`All`, `Expense`, `Income`, `Transfer`), account/wallet, category, and date range with quick presets (`This Month`, `Last Month`, `Last 30 Days`, `Clear Dates`) or custom `date_from`/`date_to` datepickers. Active filters render as an interactive tags strip (`.active-filter-strip`) with 1-tap removable pills (`✕`) and `Clear all` reset button.
- **Net Worth Growth Curve on Graphs (`/graphs/`)**: Smooth cubic-bezier line chart on `/graphs/` (`#netWorthChart` for 6-month progression in monthly mode and `#netWorthChartAnnual` for 12-month progression in annual mode). Accurately calculates total asset progression for included wallets ($\sum \text{initial} + \text{income} - \text{expense} + \text{net external transfers}$), complete with gradient fill, interactive tooltips, hero net worth display, and real-time growth badges (`+Rp... (+X%)` / `-Rp... (-X%)`).
- **Month-over-Month (MoM) Category Trend Comparison**: On `/graphs/`, category breakdown lists feature real-time Month-over-Month variance badges. For expenses, increases are flagged with coral badges (`+X% ↗`) and decreases with emerald badges (`-Y% ↘`); for income, increases are highlighted with emerald badges (`+X% ↗`) and drops with coral badges (`-Y% ↘`). Categories new to the current billing month are badged with `New ★`.
- **Self-Hosted Local Typography (100% GDPR Compliant)**: Typography (`Plus Jakarta Sans` variable 400..800 and `Herr Von Muellerhoff` cursive) is completely self-hosted as lightweight `.woff2` files in `static/fonts/` with `@font-face` rules in `wang.css`. Completely eliminates external DNS requests and telemetry to `fonts.googleapis.com` / `fonts.gstatic.com` (full GDPR compliance), speeds up initial render, and guarantees 100% offline rendering in the PWA. Preloaded in `base.html` and cached via Cache-First strategy in `sw.js`.
- **Native Android Studio WebView Wrapper (Option 3 `android/`)**: Standalone Android Studio project wrapping the hosted DOM Cloud web app. Features `CookieManager` session persistence across restarts, `WebChromeClient.onShowFileChooser()` with `FileProvider` for camera and gallery receipt photo attachments, modern `OnBackPressedCallback` history navigation, `SwipeRefreshLayout` pull-to-refresh, hardware acceleration, and edge-to-edge pastel theme styling. Includes full Android **Adaptive & Themed Icons** (`mipmap-anydpi-v26` with `<background>`, `<foreground>`, and `<monochrome>` layers across `mdpi` through `xxxhdpi`) adapting natively to Samsung One UI squircle masks, Galaxy Themes, and Material You wallpaper palettes. **Background Resume & Lifecycle Hardening**: `launchMode="singleTask"` prevents duplicate task creation when reopening from the home launcher; `onSaveInstanceState` and robust `restoreState` with `getUrl() == null` fallback in `onCreate`/`onResume` guarantees the WebView never stays blank/black after the OS trims background activities; `onRenderProcessGone` cleanly recovers if the Chromium render process is reclaimed under memory pressure. Ready to compile via lightweight CLI (`.\gradlew.bat assembleDebug`) or Android Studio.
- **Timezone-Aware History & Peak Spending Grouping**: In `dashboard` and `graphs`, transaction dates are converted to the user's active local timezone (`timezone.localtime(t.date).date()`) before grouping with `itertools.groupby` and calculating peak spending days. Completely resolves the early-morning UTC rollover bug where transactions between 00:00 and 06:59 WIB (UTC+7) were previously grouped into the prior calendar day.
- **Bottom Sheet Scroll & Pull-to-Refresh Conflict Resolution**: Integrated `@JavascriptInterface` bridge (`AndroidBridge.setScrollableActive(boolean)`) and `setOnChildScrollUpCallback` in `MainActivity.java`. When any bottom sheet (Add/Edit Transaction sheet, category grid, wallet picker, detail sheet, daily budget, multi-filters, confirmation modal) is open or being scrolled, native Android `SwipeRefreshLayout` is dynamically notified to return `true` on child scroll up, preventing downward gestures from triggering pull-to-refresh while scrolling down and then back up inside internal scroll containers. Form pages also disable pull-to-refresh to safeguard unsaved entries.
- **Note Auto-Suggestions Instant Sync & Deduplication**: Resolved the issue where newly added notes required a full page refresh to appear in suggestion chips and duplicate notes were being shown. Fixed backend SQL query in `_sheet_context` (`annotate(note_count=Count("id"), last_id=Max("id")).order_by("-note_count", "-last_id")`) so that SQL groups strictly by `note` without splitting by `id`, paired with case-insensitive Python deduplication. On the frontend, injected `{{ recent_notes|json_script:"turbo-recent-notes" }}` inside `<main>` so Turbo page-swaps carry fresh notes into the bottom sheet (`data-turbo-permanent`), added optimistic instant prepending (`addNoteToRecent`) on form submit with `localStorage` persistence, and enforced client-side case-insensitive `Set` deduplication so each unique note text is rendered at most once.
- **Real-Time Account & Wallet Picker in Transaction Sheets**: Added `/api/wallets/` endpoint returning current non-archived wallets with bulk-aggregated balances (`formatted_balance` with Indonesian grouping). Upgraded `#picker-sheet` in `_add_sheet.html` with dynamic re-rendering (`renderPickerWallets`), background fetching on sheet open (`openSheet`) and picker open (`openPicker`), Turbo page-swap synchronization (`turbo:render`), and robust event delegation on `.picker-list`. Completely eliminates stale wallet balances and missing newly-added wallets caused by the sheet's `data-turbo-permanent` DOM preservation.
- **Dual-Tier Zero-FOUT Vector SVG Sprite System (`_svg_symbols.html` + `static/img/icons.svg`)**: Replaced the heavy 5.36 MB Material Symbols font with an intelligent dual-tier SVG vector architecture:
  1. **Tier 1 (Inline Core Sprite `_svg_symbols.html`)**: 122 optimized `<symbol id="icon-...">` definitions included directly in `base.html` for 0ms instant frame-1 rendering of all core UI (appbar, bottom nav, FAB, toasts, standard categories, sheets) with zero FOUT (Flash of Unstyled Text) and zero layout shifts.
  2. **Tier 2 (Cached Master Sprite `static/img/icons.svg`)**: Full universe of all 3,909 Material Symbols (~680 KB gzipped vs 5.36 MB font) extracted from `@material-symbols/svg-400`. Pre-cached offline via PWA Service Worker (`sw.js` in `CORE_ASSETS`) and pre-fetched in `<head>` (`<link rel="prefetch">`).
  3. **Universal Fallback Engine**: Server-side `wang_icons` template library (`{% icon "name" %}`, `{% icon_href "name" %}`) and client-side helpers in `app.js` (`getIconHref(name)`, `setSvgIcon(el, name)`, and `resolveExternalIcons()`) dynamically route known core icons to local `#icon-...` and any custom or manually-typed icon to `/static/img/icons.svg#icon-...`, giving users full access to every Material Symbol without any text flicker.









## First pass
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
- Project includes `.domcloud.yml` recipe and `passenger_wsgi.py` for Passenger/Nginx deployment on DOM Cloud.
- `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` configured for reverse-proxy SSL termination.
- Production cookie security (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_BROWSER_XSS_FILTER`, `SECURE_CONTENT_TYPE_NOSNIFF`) active when `DJANGO_DEBUG=0`.
- WhiteNoise enabled with `WHITENOISE_MANIFEST_STRICT = False`.
- `requirements.txt` uses `PyMySQL`; `collectstatic` + `migrate` on deploy.
- **Logging**: Rotating file logger configured in `settings.py` writing to `logs/app.log` (5MB rotating, 5 backups) and console stream, capturing all 500 errors and tracebacks from `django.request`. `logs/` is gitignored.
- **MariaDB Timezone Resilience**: `dashboard` distinct months query uses direct `values_list("date", flat=True)` with local timezone conversion in Python, ensuring 100% compatibility across MariaDB/MySQL environments without requiring `mysql_tzinfo_to_sql` tables.
- **PWA & Mobile**: `static/manifest.json` + `static/img/logo-fix.png`, `icon-192.png`, `icon-512.png`, `apple-touch-icon.png`, `favicon.png`. Supports "Add to Home Screen" with standalone fullscreen on iOS and Android.
- **Media File Serving**: `config/urls.py` routes `re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})` and `config/settings.py` sets `MEDIA_URL = "/media/"`, allowing Django & Passenger on DOM Cloud to serve user-uploaded receipt images in both development and production.

## Conventions
- Use Decimal for money; humanize `intcomma` in templates.
- Transfers are double-entry via `from_wallet`/`out_transfers` and `to_wallet`/`in_transfers`.
- **Edge-to-Edge & Mobile Safe Space**: Android WebView runs with true edge-to-edge display (`WindowCompat.setDecorFitsSystemWindows(false)`) and transparent status and navigation bars. Real-time native system bar insets are injected into CSS custom properties (`--safe-area-top` and `--safe-area-bottom`). Appbar and bottomnav backgrounds stretch to the physical device glass, while UI controls are padded safely. In desktop view (`@media (min-width: 481px)`), safe area insets are reset to `0px !important`.
- Keep AGENTS.md updated when you add models/routes.
