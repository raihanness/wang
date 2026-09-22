# Wang

<div align="center">

**A cute, aesthetic, mobile-first personal finance and money tracking application inspired by Money+.**

[![Django](https://img.shields.io/badge/Django-5.2-092E20?style=for-the-badge&logo=django&logoColor=white)](https://www.djangoproject.com/)
[![Turbo 8](https://img.shields.io/badge/Hotwired-Turbo_8-FF4500?style=for-the-badge&logo=hotwired&logoColor=white)](https://turbo.hotwired.dev/)
[![PWA Ready](https://img.shields.io/badge/PWA-Offline_Ready-5A0FC8?style=for-the-badge&logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)
[![Android](https://img.shields.io/badge/Android-Native_WebView-3DDC84?style=for-the-badge&logo=android&logoColor=white)](https://developer.android.com/)
[![Gemini AI](https://img.shields.io/badge/Google_Gemini-Vision_AI-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

</div>

---

## Overview

**Wang** is a delightful personal finance tracking system designed from the ground up with a **mobile-first philosophy**. It heavily uses Money+ as a reference for UI/UX and features, with modern web performance engineering: instantaneous **Turbo 8** SPA navigation, zero-FOUT SVG icon architecture, tactile **Web Audio** acoustic feedback, offline **PWA** capabilities, and an on-demand **Gemini AI Receipt Scanner**.

Whether accessed in a mobile browser, installed as an offline-capable PWA, or running as a native Android APK wrapper, Wang provides an ultra-fast, native-feeling financial logging experience.

---

## Key Features

### Mobile-First Experience & Native Feel
- **480px Phone Frame**: Optimized for one-handed mobile use with centered desktop frame.
- **Fixed Bottom Navigation**: Quick access to Home, Wallets, Add (+ FAB), History, and More.
- **Buttery Bottom Sheets**: Modal interaction for adding transactions, setting daily budgets, picking accounts, selecting date-times, multi-filtering, and confirm deletions.
- **Zero-Lag Solid Surfaces**: Fast rendering with high contrast, eliminating mobile GPU compositing slowdowns.
- **Edge-to-Edge Safe Area Insets**: Transparent status and navigation bars adapting to physical device cutouts.

### Turbo 8 SPA Navigation Suite
- **Single-Page App Feel**: Hotwired Turbo 8 swaps only the `<main>` container while preserving the app shell, navigation bar, and state.
- **Touchstart / Pointerdown Preloading**: Downloads target views 150–300ms before click events fire.
- **Persistent Bottom Sheet DOM (`data-turbo-permanent`)**: Keeps the 54 KB add-transaction bottom sheet mounted across page visits.
- **Dual-Tier Zero-FOUT SVG System**: 122 inline core vector symbols (`_svg_symbols.html`) + 3,909 offline-cached Material Symbols master sprite (`icons.svg`).

### Money+ Style Add-Transaction Sheet
- **4-Column Category Grid**: Intuitive grid sorting categories dynamically by your most frequent logging habits.
- **Spacious 2-Tier Input Bar**: Wallet selector chip, note field with dynamic auto-suggestions from past history, and hero amount display.
- **Smart 4x4 Calculator Keypad**: Built-in arithmetic evaluation (`7 8 9 ÷`, `4 5 6 ×`, `1 2 3 −`, `. 0 ⌫ +`) with real-time expression previews.
- **Dynamic Note Focus Handling**: Keypad automatically hides when typing notes to give virtual keyboards ample vertical room.
- **Custom Date & Time Picker**: Built-in calendar grid with hour and minute spinners.

### AI Smart Receipt Scanner (Google Gemini)
- **1-Tap Photo Scan**: Snap or upload any paper/digital receipt to trigger on-demand Gemini Vision analysis (`gemini-3.5-flash-lite` / `gemini-3.6-flash`).
- **Automated Extraction**:
  - Total amount paid
  - Clean note string (`Merchant - Items`)
  - Auto-matched category selection
  - Payment method wallet heuristics (Cash, Debit BCA, Mandiri, QRIS, GoPay, OVO, ShopeePay)
  - Promotional discount savings badge (e.g., `Saved Rp15,000`)
- **Automated WebP Optimization**: Receipt images are automatically compressed, resized (max 1200px), and converted to WebP format upon upload.

### Multi-Wallet & Net Worth Tracking
- **Account Types**: Cash, Bank, E-Wallet, Savings, and Custom accounts with visual icon and pastel color swatch customizers.
- **3-Way Hero Switcher**: Toggle between **Spendables**, **Savings**, and combined **Net Worth** with 1-tap privacy balance eye masking (`visibility` / `visibility_off`).
- **Double-Entry Transfers**: Seamless transfers between accounts with linked balance synchronizations.
- **Manual Account Ordering**: Drag or arrange custom wallet priority order.

### Visual Analytics & Year-in-Review
- **Dual Cashflow Chart**: Side-by-side monthly Income vs. Expense comparison with net savings percentage badges.
- **Interactive Clickable Donut Chart**: Tap any pie slice or category legend item to slide up a drill-down transaction list (`#cat-tx-sheet`).
- **Net Worth Growth Curve**: 6-month and 12-month cubic-bezier asset progression tracking.
- **Month-over-Month (MoM) Comparison**: Real-time spending variance indicators (`+X% ↗` or `-Y% ↘`).
- **Annual Year-in-Review Summary**: 12-month dual cashflow breakdown, Top 3 Spending Categories podium with gold/silver/bronze medals, and year highlights.

### Daily Budgets with Real-Time Pacing
- **Dynamic Tri-Color Progress Bar**: Real-time status indicator (Emerald <60%, Amber 60–84%, Coral ≥85% or over).
- **Daily Spend Pace**: Immediate visual feedback for remaining daily allowance or overspend alerts.
- **Quick Preset Presets**: 1-tap budget adjustments (50K, 100K, 150K, 200K, 300K, 500K).

### Recurring Subscriptions & Bills
- **Flexible Billing Cycles**: Monthly, Weekly, and Yearly subscriptions.
- **Installment Tracking**: Track prior ongoing installments (`already_paid_installments`) and total planned payments.
- **1-Tap Quick Pay & Instant Undo**: Mark bills as paid with linked transaction logging, and roll back payments with 1 tap.
- **Dynamic Countdown Badges**: Real-time indicators (`Due today`, `In X days`, `Overdue`).

### Debts & Loans (Utang & Piutang)
- **Lent & Borrowed Records**: Keep track of money lent to or borrowed from others.
- **Partial Repayments & Full Settlement**: Record incremental repayments with linked transaction balance synchronization.
- **Settlement Badges**: Visual progress bars, remaining amount countdowns, and settlement status chips.

### Pastel Themes & Sound Engine
- **Zero-Flash Theme Engine**: Seamless light and dark mode switching with pre-paint theme script.
- **Web Audio Tactile Feedback**: Custom synthesized acoustic sounds (bubbles, chimes, knocks, clicks) paired with device haptics.
- **Self-Hosted Typography**: Fully self-hosted `Plus Jakarta Sans` & `Herr Von Muellerhoff` fonts (100% GDPR compliant).

### 1-Tap Excel CSV Data Export
- Export full transaction history or monthly slices into Microsoft Excel-ready UTF-8 BOM (`\ufeff`) CSV files with 1 tap.

### Native Android Client (`android/`)
- Standalone Android Studio project wrapping the web app inside an optimized hardware-accelerated `WebView`.
- Includes `WebChromeClient.onShowFileChooser()` with `FileProvider` for native camera & photo gallery receipt scanning, pull-to-refresh (`SwipeRefreshLayout`), adaptive Android icons, and session persistence.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | [Django 5.2](https://www.djangoproject.com/) (Python 3.10+) |
| **Database** | SQLite (Local Development) / MariaDB & MySQL (Production) |
| **SPA Engine** | [Hotwired Turbo 8](https://turbo.hotwired.dev/) |
| **Frontend Styling** | Vanilla CSS3 (Custom Design System, Tokens, CSS Grid, Flexbox) |
| **Icons & Typography** | Material Symbols SVG Sprite + Plus Jakarta Sans & Herr Von Muellerhoff |
| **Charts & Graphs** | [Chart.js 4](https://www.chartjs.org/) |
| **Audio & Haptics** | Web Audio API (Synthesizer Engine) + Navigator Vibration API |
| **Image Processing** | Pillow (PIL) WebP conversion & EXIF auto-rotation |
| **AI Vision Scanner** | [Google Gemini API](https://ai.google.dev/) (`gemini-3.5-flash-lite` / `gemini-3.6-flash`) |
| **WSGI / Static** | Gunicorn + WhiteNoise + Passenger WSGI |
| **Native Mobile** | Android Studio (Java, AndroidX, WebView, FileProvider) |

---

## Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- Git
- (Optional) Android Studio (if compiling the native Android wrapper)

### 2. Clone the Repository
```bash
git clone https://github.com/raihanness/wang.git
cd wang
```

### 3. Create and Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` to configure your settings (SQLite is enabled by default for local development):
```env
DJANGO_SECRET_KEY=your-local-secret-key-here
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
DJANGO_TIME_ZONE=Asia/Jakarta

# Local Database
DB_ENGINE=sqlite

# (Optional) AI Receipt Scanner
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-3.6-flash
```

### 6. Run Migrations & Start Server
```bash
python manage.py migrate
python manage.py runserver
```

Open your browser at `http://127.0.0.1:8000`. You can create a new account or create a superuser via:
```bash
python manage.py createsuperuser
```

---

## Environment Variables Reference

| Variable | Description | Default / Example |
|---|---|---|
| `DJANGO_SECRET_KEY` | Secret key for cryptographic signing | *Required in production* |
| `DJANGO_DEBUG` | Enable/disable debug mode (`1` or `0`) | `0` (Production) / `1` (Dev) |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated list of host/domain names | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated list of trusted CSRF origins | `https://yourdomain.com` |
| `DJANGO_TIME_ZONE` | Django timezone setting | `Asia/Jakarta` |
| `DB_ENGINE` | Database engine (`sqlite` or `mariadb` / `mysql`) | `sqlite` |
| `DB_NAME` | Database name (for MariaDB/MySQL) | `wang` |
| `DB_USER` | Database user (for MariaDB/MySQL) | `wang` |
| `DB_PASSWORD` | Database password (for MariaDB/MySQL) | `your-db-password` |
| `DB_HOST` | Database host | `127.0.0.1` |
| `DB_PORT` | Database port | `3306` |
| `GEMINI_API_KEY` | Google Gemini Vision API key for receipt OCR | `AIzaSy...` (Optional) |
| `GEMINI_MODEL` | Gemini model name | `gemini-3.6-flash` |

---

## Deployment (DOM Cloud / MariaDB / Passenger)

Wang is pre-configured with a `.domcloud.yml` recipe and `passenger_wsgi.py` for deployment on [DOM Cloud](https://domcloud.co/) or any Passenger/Nginx/Apache host:

1. Create a new website in DOM Cloud connected to your GitHub repository (`raihanness/wang`).
2. Configure your environment variables in the DOM Cloud environment settings.
3. Deploy! The `.domcloud.yml` script will automatically:
   - Configure Python 3.12 environment
   - Install dependencies from `requirements.txt`
   - Run database migrations (`python manage.py migrate`)
   - Collect static assets (`python manage.py collectstatic --noinput`)
   - Restart the Passenger application

---

## Building the Android APK

1. Open **Android Studio**.
2. Select **Open** and choose the `android/` directory inside this repository.
3. Update `app/src/main/res/values/strings.xml` with your live hosted URL:
   ```xml
   <string name="app_web_url">https://your-domain.domcloud.dev</string>
   ```
4. Build the debug APK via the menu (**Build > Build Bundle(s) / APK(s) > Build APK(s)**) or via terminal:
   ```bash
   cd android
   ./gradlew assembleDebug
   ```
5. Find the output APK in `android/app/build/outputs/apk/debug/app-debug.apk` and install it on your device!