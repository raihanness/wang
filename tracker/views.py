import os
from decimal import Decimal
import csv
from urllib.parse import quote_plus
from django.http import JsonResponse, HttpResponse, FileResponse
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Sum, Q, Max, Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta, date, datetime, time
import calendar
import json

from django.conf import settings
from .forms import WalletForm, CategoryForm, TransactionForm, SubscriptionForm, DebtForm, DebtPaymentForm, ProfileForm
from .models import Wallet, Category, Transaction, Subscription, SubscriptionPayment, Budget, Debt, DebtPayment, UserProfile
from .receipt_scanner import scan_receipt_with_gemini


def _month_bounds(d):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime(d.year, d.month, 1, 0, 0, 0), tz)
    last = calendar.monthrange(d.year, d.month)[1]
    end = timezone.make_aware(datetime(d.year, d.month, last, 23, 59, 59, 999999), tz)
    return start, end

def _parse_month_param(s):
    if s and len(s) == 7 and s[4] == "-":
        try:
            y, m = int(s[:4]), int(s[5:7])
            if 1 <= m <= 12:
                return date(y, m, 1)
        except ValueError:
            pass
    return timezone.localdate().replace(day=1)


def _get_months_nav(user, month):
    current = timezone.localdate().replace(day=1)
    earliest = Transaction.objects.filter(user=user).order_by("date").first()
    min_start = (current - timedelta(days=180)).replace(day=1)
    if earliest and earliest.date:
        earliest_m = timezone.localtime(earliest.date).date().replace(day=1)
        if earliest_m < min_start:
            min_start = earliest_m
    if month < min_start:
        min_start = month

    months_nav = []
    cur_m = min_start
    while cur_m <= current:
        months_nav.append({
            "date": cur_m,
            "param": cur_m.strftime("%Y-%m"),
            "label": cur_m.strftime("%b %Y"),
            "short_label": cur_m.strftime("%b"),
            "is_active": cur_m == month,
            "is_current": cur_m == current,
        })
        cur_m = (cur_m + timedelta(days=32)).replace(day=1)
    return months_nav


def _ensure_defaults(user):
    if not Category.objects.filter(user=user).exists():
        defaults = [
            ("Food", "expense", "restaurant", "#FFB5A7"),
            ("Daily", "expense", "local_cafe", "#FEC8A1"),
            ("Transport", "expense", "directions_bus", "#FCD5CE"),
            ("Social", "expense", "diversity_3", "#D8E2DC"),
            ("Housing", "expense", "home", "#E8E8A6"),
            ("Gifts", "expense", "card_giftcard", "#FFD6E0"),
            ("Communications", "expense", "cell_tower", "#C7CEEA"),
            ("Utangs", "expense", "handshake", "#B5EAD7"),
            ("Forgotten", "expense", "help", "#F4D0D0"),
            ("Work/Projects", "expense", "work", "#D6C9F0"),
            ("Electronics", "expense", "devices", "#A8D8EA"),
            ("Laptop Stuff", "expense", "laptop", "#B5EAD7"),
            ("Clothing", "expense", "checkroom", "#FEC8A1"),
            ("Entertainment", "expense", "sports_esports", "#C7CEEA"),
            ("Tax", "expense", "account_balance", "#D8E2DC"),
            ("Medical", "expense", "medical_services", "#F4D0D0"),
            ("Education", "expense", "menu_book", "#D6C9F0"),
            ("Misc", "expense", "apps", "#E5E5E5"),
            ("Mom", "income", "favorite", "#FFB5A7"),
            ("Dad", "income", "family_restroom", "#B5EAD7"),
            ("Sis", "income", "sisterhood", "#FFD6E0"),
            ("Housing", "income", "home", "#E8E8A6"),
            ("Utangs", "income", "handshake", "#C7CEEA"),
            ("Salary", "income", "payments", "#B5EAD7"),
            ("Part-time", "income", "work", "#D6C9F0"),
            ("Bonus", "income", "redeem", "#FFD6E0"),
        ]
        for name, kind, icon, color in defaults:
            Category.objects.get_or_create(user=user, name=name, kind=kind, defaults={"icon": icon, "color": color})
    if not Wallet.objects.filter(user=user).exists():
        Wallet.objects.create(user=user, name="Cash", type="cash", icon="payments", color="#FFB5A7", initial_balance=0)

from collections import defaultdict


def _compute_net_worth_trend(user, month_dates, inc_wallet_ids, initial_assets):
    """
    Computes net worth progression for included wallets across given month_dates.
    """
    if not inc_wallet_ids:
        return [], Decimal("0"), Decimal("0"), 0.0

    points = []
    for d in month_dates:
        _, m_end = _month_bounds(d)
        inc = Transaction.objects.filter(user=user, wallet_id__in=inc_wallet_ids, kind=Transaction.Kind.INCOME, date__lte=m_end).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        exp = Transaction.objects.filter(user=user, wallet_id__in=inc_wallet_ids, kind=Transaction.Kind.EXPENSE, date__lte=m_end).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        tr_in = Transaction.objects.filter(user=user, kind=Transaction.Kind.TRANSFER, to_wallet_id__in=inc_wallet_ids, date__lte=m_end).exclude(from_wallet_id__in=inc_wallet_ids).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        tr_out = Transaction.objects.filter(user=user, kind=Transaction.Kind.TRANSFER, from_wallet_id__in=inc_wallet_ids, date__lte=m_end).exclude(to_wallet_id__in=inc_wallet_ids).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        nw = initial_assets + inc - exp + tr_in - tr_out
        points.append({
            "label": d.strftime("%b %Y"),
            "short_label": d.strftime("%b"),
            "net_worth": float(nw),
        })

    start_nw = Decimal(str(points[0]["net_worth"])) if points else Decimal("0")
    end_nw = Decimal(str(points[-1]["net_worth"])) if points else Decimal("0")
    growth_amt = end_nw - start_nw
    growth_pct = round(float((growth_amt / start_nw) * 100), 1) if start_nw > 0 else 0.0

    return points, end_nw, growth_amt, growth_pct


def _get_wallets_with_balances(user, archived=False):
    wallets_qs = Wallet.objects.filter(user=user)
    if archived is not None:
        wallets_qs = wallets_qs.filter(archived=archived)
    order_fields = ["archived", "order", "name"] if archived is None else ["order", "name"]
    wallets = list(wallets_qs.order_by(*order_fields))
    if not wallets:
        return wallets

    inc_exp = (
        Transaction.objects.filter(user=user, wallet__in=wallets)
        .values("wallet_id", "kind")
        .annotate(total=Sum("amount"))
    )
    income_by_w = defaultdict(Decimal)
    expense_by_w = defaultdict(Decimal)
    for row in inc_exp:
        wid = row["wallet_id"]
        k = row["kind"]
        if k == Transaction.Kind.INCOME:
            income_by_w[wid] = row["total"] or Decimal("0")
        elif k == Transaction.Kind.EXPENSE:
            expense_by_w[wid] = row["total"] or Decimal("0")

    out_tx = (
        Transaction.objects.filter(user=user, kind=Transaction.Kind.TRANSFER, from_wallet__in=wallets)
        .values("from_wallet_id")
        .annotate(total=Sum("amount"))
    )
    out_by_w = {row["from_wallet_id"]: (row["total"] or Decimal("0")) for row in out_tx}

    in_tx = (
        Transaction.objects.filter(user=user, kind=Transaction.Kind.TRANSFER, to_wallet__in=wallets)
        .values("to_wallet_id")
        .annotate(total=Sum("amount"))
    )
    in_by_w = {row["to_wallet_id"]: (row["total"] or Decimal("0")) for row in in_tx}

    for w in wallets:
        bal = (
            w.initial_balance
            + income_by_w.get(w.id, Decimal("0"))
            - expense_by_w.get(w.id, Decimal("0"))
            - out_by_w.get(w.id, Decimal("0"))
            + in_by_w.get(w.id, Decimal("0"))
        )
        w._cached_balance = bal

    return wallets


def _sheet_context(user):
    """Data for the add-transaction bottom sheet (base.html includes it on every page)."""
    from django.db.models import Count, Max
    cats = Category.objects.filter(user=user).annotate(
        tx_count=Count("transactions")
    ).order_by("-tx_count", "name")
    raw_notes = (
        Transaction.objects.filter(user=user)
        .exclude(note="")
        .exclude(note__isnull=True)
        .values("note")
        .annotate(note_count=Count("id"), last_id=Max("id"))
        .order_by("-note_count", "-last_id")
        .values_list("note", flat=True)[:100]
    )
    seen = set()
    recent_notes = []
    for n in raw_notes:
        cleaned = n.strip()
        lower = cleaned.lower()
        if cleaned and lower not in seen:
            seen.add(lower)
            recent_notes.append(cleaned)
        if len(recent_notes) >= 60:
            break

    wallets = _get_wallets_with_balances(user, archived=False)

    # Determine default wallet from user's last added transaction
    last_tx = (
        Transaction.objects.filter(user=user)
        .order_by("-id")
        .select_related("wallet", "from_wallet")
        .first()
    )
    default_wallet = None
    if last_tx:
        cand = last_tx.wallet or last_tx.from_wallet
        if cand and not cand.archived:
            default_wallet = next((w for w in wallets if w.id == cand.id), cand)
    if not default_wallet and wallets:
        default_wallet = wallets[0]

    overall_budget = Budget.objects.filter(user=user, category__isnull=True).first()
    return {
        "expense_cats": cats.filter(kind=Category.Kind.EXPENSE),
        "income_cats": cats.filter(kind=Category.Kind.INCOME),
        "all_cats": list(cats),
        "wallets": wallets,
        "default_wallet": default_wallet,
        "recent_notes": recent_notes,
        "overall_budget": overall_budget,
    }


@login_required
def dashboard(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    wallets = ctx["wallets"]

    # home history: current month by default, ?month=YYYY-MM pages older months
    month = _parse_month_param(request.GET.get("month"))  # first of requested (default current)
    today = timezone.localdate()
    current = today.replace(day=1)
    m_start, m_end = _month_bounds(month)

    # Multi-filter parameters
    date_from_str = request.GET.get("date_from") or ""
    date_to_str = request.GET.get("date_to") or ""
    custom_dates = False

    dt_from = None
    dt_to = None
    if date_from_str:
        try:
            d_f = datetime.strptime(date_from_str, "%Y-%m-%d").date()
            dt_from = timezone.make_aware(datetime.combine(d_f, time.min))
            custom_dates = True
        except ValueError:
            date_from_str = ""
    if date_to_str:
        try:
            d_t = datetime.strptime(date_to_str, "%Y-%m-%d").date()
            dt_to = timezone.make_aware(datetime.combine(d_t, time.max))
            custom_dates = True
        except ValueError:
            date_to_str = ""

    if custom_dates:
        qs_range_start = dt_from or timezone.make_aware(datetime(2000, 1, 1, 0, 0, 0))
        qs_range_end = dt_to or timezone.make_aware(datetime(2099, 12, 31, 23, 59, 59, 999999))
        qs = Transaction.objects.filter(user=request.user, date__gte=qs_range_start, date__lte=qs_range_end)
    else:
        qs = Transaction.objects.filter(user=request.user, date__gte=m_start, date__lte=m_end)

    def _parse_csv_list(val):
        if not val:
            return []
        if isinstance(val, (list, tuple)):
            items = []
            for v in val:
                items.extend(str(v).split(","))
            return [x.strip() for x in items if x.strip()]
        return [x.strip() for x in str(val).split(",") if x.strip()]

    # Type / Kind filters
    raw_filter = request.GET.getlist("filter") or request.GET.get("filter")
    raw_filter_exclude = request.GET.getlist("filter_exclude") or request.GET.get("filter_exclude")
    filter_kinds_in = [k for k in _parse_csv_list(raw_filter) if k in ("expense", "income", "transfer")]
    filter_kinds_out = [k for k in _parse_csv_list(raw_filter_exclude) if k in ("expense", "income", "transfer")]

    if filter_kinds_in:
        qs = qs.filter(kind__in=filter_kinds_in)
    if filter_kinds_out:
        qs = qs.exclude(kind__in=filter_kinds_out)

    # Wallet filters
    raw_wallets = request.GET.getlist("wallet") or request.GET.get("wallet")
    raw_wallets_exclude = request.GET.getlist("wallet_exclude") or request.GET.get("wallet_exclude")
    wallet_ids_in = []
    for w in _parse_csv_list(raw_wallets):
        try:
            wallet_ids_in.append(int(w))
        except ValueError:
            pass
    wallet_ids_out = []
    for w in _parse_csv_list(raw_wallets_exclude):
        try:
            wallet_ids_out.append(int(w))
        except ValueError:
            pass

    selected_wallets_in = list(Wallet.objects.filter(user=request.user, pk__in=wallet_ids_in)) if wallet_ids_in else []
    selected_wallets_out = list(Wallet.objects.filter(user=request.user, pk__in=wallet_ids_out)) if wallet_ids_out else []

    if wallet_ids_in:
        qs = qs.filter(Q(wallet_id__in=wallet_ids_in) | Q(from_wallet_id__in=wallet_ids_in) | Q(to_wallet_id__in=wallet_ids_in))
    if wallet_ids_out:
        qs = qs.exclude(Q(wallet_id__in=wallet_ids_out) | Q(from_wallet_id__in=wallet_ids_out) | Q(to_wallet_id__in=wallet_ids_out))

    # Category filters
    raw_cats = request.GET.getlist("category") or request.GET.get("category")
    raw_cats_exclude = request.GET.getlist("category_exclude") or request.GET.get("category_exclude")
    cat_ids_in = []
    for c in _parse_csv_list(raw_cats):
        try:
            cat_ids_in.append(int(c))
        except ValueError:
            pass
    cat_ids_out = []
    for c in _parse_csv_list(raw_cats_exclude):
        try:
            cat_ids_out.append(int(c))
        except ValueError:
            pass

    selected_cats_in = list(Category.objects.filter(user=request.user, pk__in=cat_ids_in)) if cat_ids_in else []
    selected_cats_out = list(Category.objects.filter(user=request.user, pk__in=cat_ids_out)) if cat_ids_out else []

    if cat_ids_in:
        qs = qs.filter(category_id__in=cat_ids_in)
    if cat_ids_out:
        qs = qs.exclude(category_id__in=cat_ids_out)

    q = request.GET.get("q") or ""
    if q:
        qs = qs.filter(Q(note__icontains=q) | Q(category__name__icontains=q))

    qs = qs.select_related("wallet", "category", "from_wallet", "to_wallet").order_by("-date", "-id")
    txs = list(qs[:200])

    from itertools import groupby

    def _local_tx_date(t):
        if t.date:
            return timezone.localtime(t.date).date() if timezone.is_aware(t.date) else t.date.date()
        return None

    groups = []
    for day, grp in groupby(txs, key=_local_tx_date):
        items = list(grp)
        day_inc = sum((t.amount for t in items if t.kind == Transaction.Kind.INCOME), Decimal("0"))
        day_exp = sum((t.amount for t in items if t.kind == Transaction.Kind.EXPENSE), Decimal("0"))
        groups.append((day, items, day_exp, day_inc))

    # month totals for the balance header
    if custom_dates:
        income_month = qs.filter(kind=Transaction.Kind.INCOME).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        expense_month = qs.filter(kind=Transaction.Kind.EXPENSE).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        month_label = f"{date_from_str or '...'} – {date_to_str or '...'}"
    else:
        qs_month = Transaction.objects.filter(user=request.user, date__gte=m_start, date__lte=m_end)
        income_month = qs_month.filter(kind=Transaction.Kind.INCOME).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        expense_month = qs_month.filter(kind=Transaction.Kind.EXPENSE).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        month_label = month.strftime("%B %Y")
    spendable_balance = sum((w.current_balance for w in wallets if w.include_in_total and w.type != Wallet.WalletType.SAVINGS and not w.archived), Decimal("0"))
    savings_balance = sum((w.current_balance for w in wallets if (not w.include_in_total or w.type == Wallet.WalletType.SAVINGS) and not w.archived), Decimal("0"))
    net_worth = spendable_balance + savings_balance
    total_balance = spendable_balance

    # month paging: back always when older data exists, forward only when past the current month
    is_current = month == current

    def _build_filter_url(remove_type=None, remove_type_exclude=None,
                          remove_wallet=None, remove_wallet_exclude=None,
                          remove_cat=None, remove_cat_exclude=None,
                          remove_dates=False):
        p = []
        if not custom_dates and not is_current:
            p.append(f"month={month.strftime('%Y-%m')}")
        if q:
            p.append(f"q={quote_plus(q)}")

        rem_t_in = [t for t in filter_kinds_in if t != remove_type]
        if rem_t_in:
            p.append(f"filter={','.join(rem_t_in)}")

        rem_t_out = [t for t in filter_kinds_out if t != remove_type_exclude]
        if rem_t_out:
            p.append(f"filter_exclude={','.join(rem_t_out)}")

        rem_w_in = [w for w in wallet_ids_in if w != remove_wallet]
        if rem_w_in:
            p.append(f"wallet={','.join(map(str, rem_w_in))}")

        rem_w_out = [w for w in wallet_ids_out if w != remove_wallet_exclude]
        if rem_w_out:
            p.append(f"wallet_exclude={','.join(map(str, rem_w_out))}")

        rem_c_in = [c for c in cat_ids_in if c != remove_cat]
        if rem_c_in:
            p.append(f"category={','.join(map(str, rem_c_in))}")

        rem_c_out = [c for c in cat_ids_out if c != remove_cat_exclude]
        if rem_c_out:
            p.append(f"category_exclude={','.join(map(str, rem_c_out))}")

        if custom_dates and not remove_dates:
            if date_from_str:
                p.append(f"date_from={date_from_str}")
            if date_to_str:
                p.append(f"date_to={date_to_str}")
        query_str = "&".join(p)
        return f"{reverse('dashboard')}?{query_str}" if query_str else reverse("dashboard")

    active_filter_tags = []
    active_filter_count = 0

    for k in filter_kinds_in:
        active_filter_count += 1
        active_filter_tags.append({
            "key": "filter",
            "is_exclude": False,
            "label": k.title(),
            "icon": "trending_down" if k == "expense" else ("trending_up" if k == "income" else "send_money"),
            "remove_url": _build_filter_url(remove_type=k),
        })

    for k in filter_kinds_out:
        active_filter_count += 1
        active_filter_tags.append({
            "key": "filter",
            "is_exclude": True,
            "label": f"Exclude {k.title()}",
            "icon": "trending_down" if k == "expense" else ("trending_up" if k == "income" else "send_money"),
            "remove_url": _build_filter_url(remove_type_exclude=k),
        })

    for w in selected_wallets_in:
        active_filter_count += 1
        active_filter_tags.append({
            "key": "wallet",
            "is_exclude": False,
            "label": w.name,
            "icon": w.icon,
            "color": w.color,
            "remove_url": _build_filter_url(remove_wallet=w.id),
        })

    for w in selected_wallets_out:
        active_filter_count += 1
        active_filter_tags.append({
            "key": "wallet",
            "is_exclude": True,
            "label": f"Exclude {w.name}",
            "icon": w.icon,
            "color": w.color,
            "remove_url": _build_filter_url(remove_wallet_exclude=w.id),
        })

    for c in selected_cats_in:
        active_filter_count += 1
        active_filter_tags.append({
            "key": "category",
            "is_exclude": False,
            "label": c.name,
            "icon": c.icon,
            "color": c.color,
            "remove_url": _build_filter_url(remove_cat=c.id),
        })

    for c in selected_cats_out:
        active_filter_count += 1
        active_filter_tags.append({
            "key": "category",
            "is_exclude": True,
            "label": f"Exclude {c.name}",
            "icon": c.icon,
            "color": c.color,
            "remove_url": _build_filter_url(remove_cat_exclude=c.id),
        })

    if custom_dates:
        active_filter_count += 1
        d_lbl = f"{date_from_str or '...'} → {date_to_str or '...'}"
        active_filter_tags.append({
            "key": "dates",
            "is_exclude": False,
            "label": d_lbl,
            "icon": "calendar_month",
            "remove_url": _build_filter_url(remove_dates=True),
        })
    prev_month = (month - timedelta(days=1)).replace(day=1)
    next_month = (month + timedelta(days=32)).replace(day=1)
    has_older = Transaction.objects.filter(user=request.user, date__lt=m_start).exists()
    has_newer = not is_current  # let user page forward until current month

    # horizontal month scroll navigation (earliest transaction to current month, min 6 months)
    months_nav = _get_months_nav(request.user, month)

    # query distinct months that have transactions for this user
    # Note: Extract local YYYY-MM directly from transaction dates to guarantee 100% portability
    # across MariaDB/MySQL installations on shared hosts without mysql_tzinfo_to_sql timezone tables.
    tx_months = set()
    for dt in Transaction.objects.filter(user=request.user).values_list("date", flat=True):
        if dt:
            loc = timezone.localtime(dt) if timezone.is_aware(dt) else dt
            tx_months.add(loc.strftime("%Y-%m"))
    tx_months.add(current.strftime("%Y-%m"))
    tx_months.add(month.strftime("%Y-%m"))

    years_with_data = [int(m.split("-")[0]) for m in tx_months]
    min_year = min(years_with_data) if years_with_data else current.year
    max_year = max(years_with_data) if years_with_data else current.year

    popover_months = []
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    view_year = month.year
    for i, name in enumerate(month_names, start=1):
        m_str = f"{i:02d}"
        ym = f"{view_year}-{m_str}"
        has_data = ym in tx_months
        is_active = (ym == month.strftime("%Y-%m"))
        is_current_m = (ym == current.strftime("%Y-%m"))
        popover_months.append({
            "num": m_str,
            "name": name,
            "ym": ym,
            "has_data": has_data,
            "is_active": is_active,
            "is_current": is_current_m,
        })

    # auto-open edit sheet if ?edit=<id> is requested
    edit_id = request.GET.get("edit")
    edit_tx = None
    if edit_id:
        try:
            edit_tx = Transaction.objects.select_related("category", "wallet", "from_wallet", "to_wallet").get(pk=edit_id, user=request.user)
        except (Transaction.DoesNotExist, ValueError):
            pass

    # today's summary metrics
    today_start = timezone.make_aware(datetime.combine(today, time.min))
    today_end = timezone.make_aware(datetime.combine(today, time.max))
    qs_today = Transaction.objects.filter(user=request.user, date__gte=today_start, date__lte=today_end)
    today_income = qs_today.filter(kind=Transaction.Kind.INCOME).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    today_expense = qs_today.filter(kind=Transaction.Kind.EXPENSE).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    today_net = today_income - today_expense

    # active subscriptions sorted by upcoming due date (excluding finished/completed)
    all_subs = list(
        Subscription.objects.filter(user=request.user, active=True)
        .select_related("wallet", "category")
        .prefetch_related("payments", "payments__wallet")
    )
    all_subs = [s for s in all_subs if not s.is_completed]
    all_subs.sort(key=lambda s: s.days_until_due)
    upcoming_subs = [s for s in all_subs if s.days_until_due <= 7]

    # active debts (unsettled) sorted by upcoming deadline
    active_debts = list(
        Debt.objects.filter(user=request.user)
        .exclude(status=Debt.Status.SETTLED)
        .select_related("wallet")
        .prefetch_related("payments")
    )
    active_debts.sort(key=lambda d: (0 if d.days_until_due is not None else 1, d.days_until_due if d.days_until_due is not None else 9999))

    # daily budget calculation
    overall_budget = Budget.objects.filter(user=request.user, category__isnull=True).first()
    budget_info = None
    if overall_budget and overall_budget.amount > 0:
        b_amt = overall_budget.amount
        b_spent = today_expense
        b_remaining = max(Decimal("0"), b_amt - b_spent)
        b_over = max(Decimal("0"), b_spent - b_amt)
        b_pct = round(min(100, float((b_spent / b_amt) * 100)), 1)

        if b_over > 0:
            status_class = "budget-over"
            status_label = "Over limit"
            status_icon = "cancel"
        elif b_pct >= 85:
            status_class = "budget-danger"
            status_label = "Almost at limit"
            status_icon = "error"
        elif b_pct >= 60:
            status_class = "budget-warning"
            status_label = "Pacing well"
            status_icon = "warning"
        else:
            status_class = "budget-good"
            status_label = "Under budget"
            status_icon = "check_circle"

        budget_info = {
            "amount": b_amt,
            "spent": b_spent,
            "remaining": b_remaining,
            "over": b_over,
            "pct": f"{b_pct:.1f}",
            "status_class": status_class,
            "status_label": status_label,
            "status_icon": status_icon,
        }

    balance_change = income_month - expense_month
    balance_change_abs = abs(balance_change)
    total_cf = income_month + expense_month
    if total_cf > 0:
        inc_val = round(float((income_month / total_cf) * 100), 1)
        cashflow_inc_pct = f"{inc_val:.1f}"
        cashflow_exp_pct = f"{(100.0 - inc_val):.1f}"
    else:
        cashflow_inc_pct = "0"
        cashflow_exp_pct = "0"

    ctx.update({
        "wallets": wallets,
        "total_balance": total_balance,
        "spendable_balance": spendable_balance,
        "net_worth": net_worth,
        "savings_balance": savings_balance,
        "income_month": income_month,
        "expense_month": expense_month,
        "month_label": month_label,
        "balance_change": balance_change,
        "balance_change_abs": balance_change_abs,
        "cashflow_inc_pct": cashflow_inc_pct,
        "cashflow_exp_pct": cashflow_exp_pct,
        "filter_kinds_in": ",".join(filter_kinds_in),
        "filter_kinds_out": ",".join(filter_kinds_out),
        "wallet_ids_in": ",".join(map(str, wallet_ids_in)),
        "wallet_ids_out": ",".join(map(str, wallet_ids_out)),
        "cat_ids_in": ",".join(map(str, cat_ids_in)),
        "cat_ids_out": ",".join(map(str, cat_ids_out)),
        "selected_wallet_id": ",".join(map(str, wallet_ids_in)) if wallet_ids_in else "",
        "selected_category_id": ",".join(map(str, cat_ids_in)) if cat_ids_in else "",
        "date_from": date_from_str,
        "date_to": date_to_str,
        "custom_dates": custom_dates,
        "active_filter_tags": active_filter_tags,
        "active_filter_count": active_filter_count,
        "today_income": today_income,
        "today_expense": today_expense,
        "today_net": today_net,
        "today_date": today,
        "history_groups": groups,
        "q": q or "",
        "active_filter": ",".join(filter_kinds_in) if filter_kinds_in else "",
        "view_month": month,
        "is_current": is_current,
        "prev_month": prev_month,
        "next_month": next_month,
        "has_older": has_older,
        "has_newer": has_newer,
        "months_nav": months_nav,
        "available_months": tx_months,
        "available_months_json": json.dumps(sorted(list(tx_months))),
        "min_year": min_year,
        "max_year": max_year,
        "popover_months": popover_months,
        "edit_tx": edit_tx,
        "all_subs": all_subs,
        "upcoming_subs": upcoming_subs,
        "active_debts": active_debts,
        "overall_budget": overall_budget,
        "budget_info": budget_info,
    })
    return render(request, "tracker/dashboard.html", ctx)



@login_required
def graphs(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    mode = request.GET.get("mode") or "month"
    today = timezone.localdate()
    current_m = today.replace(day=1)
    tz = timezone.get_current_timezone()

    # Determine available years for bounds
    tx_years = set()
    for dt in Transaction.objects.filter(user=request.user).values_list("date", flat=True):
        if dt:
            loc = timezone.localtime(dt) if timezone.is_aware(dt) else dt
            tx_years.add(loc.year)
    tx_years.add(today.year)
    min_year = min(tx_years)
    max_year = max(tx_years)

    if mode == "year":
        try:
            sel_year = int(request.GET.get("year", today.year))
        except (ValueError, TypeError):
            sel_year = today.year
        sel_year = max(min_year, min(max_year, sel_year))

        y_start = timezone.make_aware(datetime(sel_year, 1, 1, 0, 0, 0), tz)
        y_end = timezone.make_aware(datetime(sel_year, 12, 31, 23, 59, 59, 999999), tz)
        qs_year = Transaction.objects.filter(user=request.user, date__gte=y_start, date__lte=y_end)

        annual_income = qs_year.filter(kind=Transaction.Kind.INCOME).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        annual_expense = qs_year.filter(kind=Transaction.Kind.EXPENSE).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        annual_net = annual_income - annual_expense
        annual_savings_rate = round(float((annual_net / annual_income) * 100), 1) if annual_income > 0 else 0

        # 12-month dual trend breakdown
        year_trend = []
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        best_month_net = None
        best_month_name = None
        highest_spend_amt = Decimal("0")
        highest_spend_name = None

        for m_idx in range(1, 13):
            d_m = date(sel_year, m_idx, 1)
            ts, te = _month_bounds(d_m)
            m_inc = qs_year.filter(kind=Transaction.Kind.INCOME, date__gte=ts, date__lte=te).aggregate(s=Sum("amount"))["s"] or Decimal("0")
            m_exp = qs_year.filter(kind=Transaction.Kind.EXPENSE, date__gte=ts, date__lte=te).aggregate(s=Sum("amount"))["s"] or Decimal("0")
            m_net = m_inc - m_exp
            m_rate = round(float((m_net / m_inc) * 100), 1) if m_inc > 0 else 0

            m_label = month_names[m_idx - 1]
            year_trend.append({
                "label": m_label,
                "income": float(m_inc),
                "expense": float(m_exp),
                "net": float(m_net),
                "savings_rate": m_rate,
            })

            # Check highlights
            if m_inc > 0 or m_exp > 0:
                if best_month_net is None or m_net > best_month_net:
                    best_month_net = m_net
                    best_month_name = m_label
                if m_exp > highest_spend_amt:
                    highest_spend_amt = m_exp
                    highest_spend_name = m_label

        # Top expense categories for the entire year
        top_cats = list(
            qs_year.filter(kind=Transaction.Kind.EXPENSE)
            .values("category__name", "category__color", "category__icon")
            .annotate(total=Sum("amount"))
            .order_by("-total")
        )
        for r in top_cats:
            r["pct"] = round(float(r["total"] / annual_expense * 100), 1) if annual_expense > 0 else 0

        # Top 3 podium categories
        podium_ranks = [
            {"rank": 1, "icon": "workspace_premium"},
            {"rank": 2, "icon": "workspace_premium"},
            {"rank": 3, "icon": "workspace_premium"},
        ]
        top_3_cats = []
        for i, c in enumerate(top_cats[:3]):
            c_copy = dict(c)
            c_copy["rank"] = podium_ranks[i]["rank"]
            c_copy["medal_icon"] = podium_ranks[i]["icon"]
            c_copy["medal"] = podium_ranks[i]["icon"]
            top_3_cats.append(c_copy)


        # Monthly avg spending
        months_tracked = today.month if (sel_year == today.year) else 12
        monthly_avg_spend = (annual_expense / Decimal(str(months_tracked))) if months_tracked > 0 else Decimal("0")

        # 12-Month Net Worth Progression
        inc_wallets = Wallet.objects.filter(user=request.user, include_in_total=True, archived=False)
        inc_wallet_ids = list(inc_wallets.values_list("id", flat=True))
        initial_assets = sum((w.initial_balance for w in inc_wallets), Decimal("0"))
        nw_dates_year = [date(sel_year, m_idx, 1) for m_idx in range(1, 13)]
        nw_points_year, nw_end_year, nw_growth_amt_year, nw_growth_pct_year = _compute_net_worth_trend(
            request.user, nw_dates_year, inc_wallet_ids, initial_assets
        )

        ctx.update({
            "mode": "year",
            "current_year": today.year,
            "sel_year": sel_year,
            "min_year": min_year,
            "max_year": max_year,
            "prev_year": sel_year - 1 if sel_year > min_year else None,
            "next_year": sel_year + 1 if sel_year < max_year else None,
            "annual_income": annual_income,
            "annual_expense": annual_expense,
            "annual_net": annual_net,
            "annual_savings_rate": annual_savings_rate,
            "year_trend_json": year_trend,
            "top_cats": top_cats,
            "top_3_cats": top_3_cats,
            "best_month_name": best_month_name,
            "best_month_net": best_month_net,
            "highest_spend_name": highest_spend_name,
            "highest_spend_amt": highest_spend_amt,
            "monthly_avg_spend": monthly_avg_spend,
            "months_tracked": months_tracked,
            "net_worth_points": nw_points_year,
            "net_worth_end": nw_end_year,
            "net_worth_growth_amt": nw_growth_amt_year,
            "net_worth_growth_pct": nw_growth_pct_year,
            "net_worth_trend_json": nw_points_year,
        })
        return render(request, "tracker/graphs.html", ctx)

    # Monthly mode (default)
    sel = _parse_month_param(request.GET.get("month"))
    kind = request.GET.get("kind")
    if kind not in ("income", "expense"):
        kind = "expense"
    s, e = _month_bounds(sel)
    qs_month = Transaction.objects.filter(user=request.user, date__gte=s, date__lte=e)
    by_cat = (
        qs_month.filter(kind=kind)
        .values("category__id", "category__name", "category__color", "category__icon")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    total = sum((r["total"] for r in by_cat), Decimal("0"))
    by_cat_list = list(by_cat)
    for r in by_cat_list:
        r["pct"] = round(float(r["total"] / total * 100), 1) if total > 0 else 0

    # Group transactions for the category drill-down sheet
    month_txs = (
        qs_month.filter(kind=kind)
        .select_related("category", "wallet")
        .order_by("-date", "-id")
    )
    from collections import defaultdict
    cat_tx_map = defaultdict(list)
    for t in month_txs:
        cat_key = str(t.category_id or 0)
        loc_dt = timezone.localtime(t.date) if timezone.is_aware(t.date) else t.date
        cat_tx_map[cat_key].append({
            "id": t.pk,
            "amount": float(t.amount),
            "formatted_amount": f"Rp{int(t.amount):,}".replace(",", "."),
            "note": t.note or "",
            "date": loc_dt.strftime("%Y-%m-%dT%H:%M"),
            "date_display": loc_dt.strftime("%A, %B %d, %Y"),
            "time_display": loc_dt.strftime("%H:%M"),
            "datetime_display": loc_dt.strftime("%b %d, %Y · %H:%M"),
            "cat_id": t.category_id or "",
            "cat_name": t.category.name if t.category else "Uncategorized",
            "cat_icon": t.category.icon if t.category else "label",
            "cat_color": t.category.color if t.category else "#FFB5A7",
            "wallet_id": t.wallet_id or "",
            "wallet_name": t.wallet.name if t.wallet else "Account",
            "wallet_icon": t.wallet.icon if t.wallet else "account_balance_wallet",
            "kind": t.kind,
            "image": t.image.url if t.image else "",
            "edit_url": reverse("transaction_edit", args=[t.pk]),
            "delete_url": reverse("transaction_delete", args=[t.pk]),
        })

    # Month-over-Month (MoM) Category Comparison
    prev_m = (sel - timedelta(days=1)).replace(day=1)
    ps, pe = _month_bounds(prev_m)
    qs_prev = Transaction.objects.filter(user=request.user, date__gte=ps, date__lte=pe, kind=kind)
    prev_by_cat = {
        r["category__name"]: r["total"]
        for r in qs_prev.values("category__name").annotate(total=Sum("amount"))
    }

    for r in by_cat_list:
        c_name = r["category__name"]
        cur_total = r["total"]
        prev_total = prev_by_cat.get(c_name, Decimal("0"))
        r["prev_total"] = prev_total
        diff = cur_total - prev_total
        r["diff"] = diff
        if prev_total > 0:
            pct_change = round(float((diff / prev_total) * 100), 1)
            r["pct_change"] = pct_change
            r["is_new"] = False
            if diff > 0:
                r["trend_dir"] = "up"
            elif diff < 0:
                r["trend_dir"] = "down"
            else:
                r["trend_dir"] = "flat"
        else:
            r["pct_change"] = None
            r["is_new"] = True
            r["trend_dir"] = "new"

    # Daily Average Spending & Projection
    days_in_month = calendar.monthrange(sel.year, sel.month)[1]
    is_sel_current = (sel.year == today.year and sel.month == today.month)
    days_elapsed = min(today.day, days_in_month) if is_sel_current else days_in_month
    daily_avg = (total / Decimal(str(days_elapsed))) if days_elapsed > 0 else Decimal("0")
    projected_total = (daily_avg * Decimal(str(days_in_month))) if is_sel_current else total

    # Peak spending day
    peak_info = None
    from collections import defaultdict
    day_totals = defaultdict(Decimal)
    for t in qs_month.filter(kind=kind):
        d = timezone.localtime(t.date).date() if timezone.is_aware(t.date) else t.date.date()
        day_totals[d] += t.amount
    if day_totals:
        peak_date, peak_amt = max(day_totals.items(), key=lambda item: item[1])
        peak_info = {"date": peak_date.strftime("%b %d"), "amount": peak_amt}

    # 6-Month Dual Cashflow Trend (Income vs Expense + Net + Savings Rate)
    trend = []
    tot_inc_6m = Decimal("0")
    tot_exp_6m = Decimal("0")
    for i in range(5, -1, -1):
        y = sel.year
        m = sel.month - i
        while m <= 0:
            m += 12
            y -= 1
        d = date(y, m, 1)
        ts, te = _month_bounds(d)
        v_inc = Transaction.objects.filter(user=request.user, kind=Transaction.Kind.INCOME, date__gte=ts, date__lte=te).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        v_exp = Transaction.objects.filter(user=request.user, kind=Transaction.Kind.EXPENSE, date__gte=ts, date__lte=te).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        v_net = v_inc - v_exp
        rate = round(float((v_net / v_inc) * 100), 1) if v_inc > 0 else 0
        tot_inc_6m += v_inc
        tot_exp_6m += v_exp
        trend.append({
            "label": d.strftime("%b"),
            "income": float(v_inc),
            "expense": float(v_exp),
            "net": float(v_net),
            "savings_rate": rate,
            "value": float(v_exp if kind == "expense" else v_inc)
        })

    avg_6m_income = tot_inc_6m / Decimal("6")
    avg_6m_expense = tot_exp_6m / Decimal("6")
    avg_6m_net = avg_6m_income - avg_6m_expense
    avg_6m_rate = round(float((avg_6m_net / avg_6m_income) * 100), 1) if avg_6m_income > 0 else 0

    # 6-Month Net Worth Progression
    inc_wallets = Wallet.objects.filter(user=request.user, include_in_total=True, archived=False)
    inc_wallet_ids = list(inc_wallets.values_list("id", flat=True))
    initial_assets = sum((w.initial_balance for w in inc_wallets), Decimal("0"))
    nw_dates = []
    for i in range(5, -1, -1):
        y = sel.year
        m = sel.month - i
        while m <= 0:
            m += 12
            y -= 1
        nw_dates.append(date(y, m, 1))
    nw_points, nw_end, nw_growth_amt, nw_growth_pct = _compute_net_worth_trend(
        request.user, nw_dates, inc_wallet_ids, initial_assets
    )

    next_m = (sel + timedelta(days=32)).replace(day=1)
    current = timezone.localdate().replace(day=1)
    has_older = Transaction.objects.filter(user=request.user, date__lt=s).exists()
    has_newer = sel < current
    ctx.update({
        "mode": "month",
        "current_year": today.year,
        "sel_year": sel.year,
        "sel_month": sel,
        "kind": kind,
        "by_cat": by_cat_list,
        "total": total,
        "daily_avg": daily_avg,
        "projected_total": projected_total,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "is_sel_current": is_sel_current,
        "peak_info": peak_info,
        "trend_json": trend,
        "pie_json": [
            {
                "id": r["category__id"],
                "label": r["category__name"],
                "icon": r["category__icon"],
                "count": r["count"],
                "value": float(r["total"]),
                "color": r["category__color"],
                "pct": r["pct"],
                "pct_change": r["pct_change"],
                "prev_total": float(r["prev_total"]),
                "diff": float(r["diff"]),
                "is_new": r["is_new"],
                "trend_dir": r["trend_dir"],
            }
            for r in by_cat_list
        ],
        "cat_tx_json": dict(cat_tx_map),
        "avg_6m_income": avg_6m_income,
        "avg_6m_expense": avg_6m_expense,
        "avg_6m_net": avg_6m_net,
        "avg_6m_rate": avg_6m_rate,
        "net_worth_points": nw_points,
        "net_worth_end": nw_end,
        "net_worth_growth_amt": nw_growth_amt,
        "net_worth_growth_pct": nw_growth_pct,
        "net_worth_trend_json": nw_points,
        "prev_month": prev_m,
        "next_month": next_m,
        "has_older": has_older,
        "has_newer": has_newer,
        "months_nav": _get_months_nav(request.user, sel),
    })
    return render(request, "tracker/graphs.html", ctx)


@login_required
def wallet_balances_api(request):
    wallets = _get_wallets_with_balances(request.user, archived=False)
    data = []
    for w in wallets:
        bal = getattr(w, "_cached_balance", w.current_balance)
        bal_int = int(round(bal))
        prefix = "Rp" if bal_int >= 0 else "-Rp"
        formatted_bal = f"{prefix}{intcomma(abs(bal_int))}"
        data.append({
            "id": w.id,
            "name": w.name,
            "type": w.type,
            "type_display": w.get_type_display(),
            "icon": w.icon,
            "color": w.color,
            "balance": float(bal),
            "formatted_balance": formatted_bal,
        })
    return JsonResponse({"wallets": data})


@login_required
def wallet_list(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    wallets = _get_wallets_with_balances(request.user, archived=None)
    spendable_balance = sum((w.current_balance for w in wallets if w.include_in_total and w.type != Wallet.WalletType.SAVINGS and not w.archived), Decimal("0"))
    savings_balance = sum((w.current_balance for w in wallets if (not w.include_in_total or w.type == Wallet.WalletType.SAVINGS) and not w.archived), Decimal("0"))
    net_worth = spendable_balance + savings_balance
    total_balance = spendable_balance

    now = timezone.localdate()
    current_m = date(now.year, now.month, 1)
    s, e = _month_bounds(current_m)
    qs_month = Transaction.objects.filter(user=request.user, date__gte=s, date__lte=e)
    income_month = qs_month.filter(kind=Transaction.Kind.INCOME).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    expense_month = qs_month.filter(kind=Transaction.Kind.EXPENSE).aggregate(s=Sum("amount"))["s"] or Decimal("0")

    ctx.update({
        "wallets": wallets,
        "total_balance": total_balance,
        "spendable_balance": spendable_balance,
        "savings_balance": savings_balance,
        "net_worth": net_worth,
        "income_month": income_month,
        "expense_month": expense_month,
        "balance_change": income_month - expense_month,
    })
    return render(request, "tracker/wallet_list.html", ctx)

@login_required
def wallet_create(request):
    form = WalletForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        w = form.save(commit=False)
        w.user = request.user
        max_order = Wallet.objects.filter(user=request.user).aggregate(m=Max("order"))["m"]
        w.order = (max_order + 1) if max_order is not None else 0
        w.save()
        messages.success(request, f"Wallet '{w.name}' created.")
        return redirect("wallet_list")
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title="New wallet")
    return render(request, "tracker/wallet_form.html", ctx)

@login_required
def wallet_edit(request, pk):
    w = get_object_or_404(Wallet, pk=pk, user=request.user)
    form = WalletForm(request.POST or None, instance=w)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Wallet updated.")
        return redirect("wallet_list")
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title=f"Edit {w.name}", wallet_pk=w.pk)
    return render(request, "tracker/wallet_form.html", ctx)

@login_required
def wallet_delete(request, pk):
    w = get_object_or_404(Wallet, pk=pk, user=request.user)

    # Protect against deleting the user's only remaining wallet
    total_wallets = Wallet.objects.filter(user=request.user).count()
    if total_wallets <= 1:
        messages.error(request, "Cannot delete your only remaining wallet. You must have at least one account.")
        return redirect("wallet_list")

    if request.method == "POST":
        name = w.name
        w.delete()
        messages.success(request, f"Wallet '{name}' deleted.")
        return redirect("wallet_list")

    # Check for associated transactions
    tx_count = Transaction.objects.filter(
        Q(wallet=w) | Q(from_wallet=w) | Q(to_wallet=w),
        user=request.user,
    ).count()
    warning = None
    if tx_count > 0:
        warning = f"Warning: Deleting this wallet will also permanently delete {tx_count} associated transaction{'s' if tx_count > 1 else ''}."

    ctx = _sheet_context(request.user)
    ctx.update(obj=w, back="wallet_list", warning=warning)
    return render(request, "tracker/confirm_delete.html", ctx)

@login_required
def wallet_toggle_archive(request, pk):
    w = get_object_or_404(Wallet, pk=pk, user=request.user)
    w.archived = not w.archived
    w.save(update_fields=["archived"])
    return redirect("wallet_list")

@login_required
def wallet_toggle_total(request, pk):
    w = get_object_or_404(Wallet, pk=pk, user=request.user)
    w.include_in_total = not w.include_in_total
    w.save(update_fields=["include_in_total"])
    status = "included in" if w.include_in_total else "excluded from"
    messages.success(request, f"'{w.name}' is now {status} total balance.")
    return redirect("wallet_list")

@login_required
@require_POST
def wallet_reorder(request):
    try:
        data = json.loads(request.body)
        order_ids = data.get("order", [])
    except Exception:
        order_ids = request.POST.getlist("order[]") or request.POST.getlist("order")

    if order_ids:
        for index, w_id in enumerate(order_ids):
            try:
                Wallet.objects.filter(user=request.user, pk=int(w_id)).update(order=index)
            except (ValueError, TypeError):
                pass
        return JsonResponse({"status": "ok"})
    return JsonResponse({"status": "error", "message": "No order provided"}, status=400)


@login_required
def category_list(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    ctx["cats"] = Category.objects.filter(user=request.user).order_by("kind", "name")
    return render(request, "tracker/category_list.html", ctx)

@login_required
def category_create(request):
    form = CategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        c = form.save(commit=False)
        c.user = request.user
        c.save()
        messages.success(request, f"Category '{c.name}' created.")
        return redirect("category_list")
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title="New category")
    return render(request, "tracker/category_form.html", ctx)

@login_required
def category_edit(request, pk):
    c = get_object_or_404(Category, pk=pk, user=request.user)
    form = CategoryForm(request.POST or None, instance=c)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category updated.")
        return redirect("category_list")
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title=f"Edit {c.name}", category_pk=c.pk, category=c)
    return render(request, "tracker/category_form.html", ctx)

@login_required
def category_delete(request, pk):
    c = get_object_or_404(Category, pk=pk, user=request.user)
    if request.method == "POST":
        c.delete()
        messages.success(request, "Category deleted.")
        return redirect("category_list")
    ctx = _sheet_context(request.user)
    ctx.update(obj=c, back="category_list")
    return render(request, "tracker/confirm_delete.html", ctx)


@login_required
def transaction_list(request):
    qs = Transaction.objects.filter(user=request.user).select_related("wallet", "category", "from_wallet", "to_wallet")
    kind = request.GET.get("kind")
    wallet = request.GET.get("wallet")
    q = request.GET.get("q")
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    if kind in ("income", "expense", "transfer"):
        qs = qs.filter(kind=kind)
    if wallet:
        qs = qs.filter(Q(wallet_id=wallet) | Q(from_wallet_id=wallet) | Q(to_wallet_id=wallet))
    if q:
        qs = qs.filter(Q(note__icontains=q) | Q(category__name__icontains=q))
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    wallets = Wallet.objects.filter(user=request.user, archived=False)
    ctx = _sheet_context(request.user)
    ctx.update(transactions=qs[:200], wallets=wallets)
    return render(request, "tracker/transaction_list.html", ctx)

@login_required
def transaction_create(request):
    form = TransactionForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            t = form.save(commit=False)
            t.user = request.user
            t.save()
            messages.success(request, "Transaction added.")
            return redirect("dashboard")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.capitalize()}: {err}" if field != '__all__' else err)
    status_code = 422 if request.method == "POST" and not form.is_valid() else 200
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title="New transaction")
    return render(request, "tracker/transaction_form.html", ctx, status=status_code)

@login_required
def transaction_edit(request, pk):
    t = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == "POST":
        form = TransactionForm(request.POST, request.FILES, instance=t, user=request.user)
        if form.is_valid():
            tx = form.save(commit=False)
            if request.POST.get("image_clear") == "1" and not request.FILES.get("image"):
                tx.image = None
            tx.save()
            form.save_m2m()
            messages.success(request, "Transaction updated.")
            return redirect("dashboard")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.capitalize()}: {err}" if field != '__all__' else err)
            status_code = 422
            ctx = _sheet_context(request.user)
            ctx.update(form=form, title="Edit transaction")
            return render(request, "tracker/transaction_form.html", ctx, status=status_code)

    # On GET: redirect to dashboard with ?edit=<pk> so it opens in the bottom sheet
    t_month = timezone.localtime(t.date).date().replace(day=1).strftime("%Y-%m")
    return redirect(f"/?month={t_month}&edit={t.pk}")

@login_required
def transaction_delete(request, pk):
    t = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == "POST":
        t_month = timezone.localtime(t.date).date().replace(day=1).strftime("%Y-%m")
        t.delete()
        messages.success(request, "Transaction deleted.")
        return redirect(f"/?month={t_month}")
    ctx = _sheet_context(request.user)
    ctx.update(obj=t, back="dashboard")
    return render(request, "tracker/confirm_delete.html", ctx)


# ── Subscriptions & Recurring Bills ───────────────────────────
@login_required
def subscription_list(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    subs = list(
        Subscription.objects.filter(user=request.user)
        .select_related("wallet", "category")
        .prefetch_related("payments", "payments__wallet")
    )
    # Sort: active upcoming first, then completed or inactive, then by due date
    subs.sort(key=lambda s: (1 if s.is_completed else 0, 1 if not s.active else 0, s.days_until_due))
    monthly_total = Decimal("0")
    for s in subs:
        if not s.active or s.is_completed:
            continue
        if s.cycle == Subscription.Cycle.MONTHLY:
            monthly_total += s.amount
        elif s.cycle == Subscription.Cycle.YEARLY:
            monthly_total += (s.amount / Decimal("12"))
        elif s.cycle == Subscription.Cycle.WEEKLY:
            monthly_total += (s.amount * Decimal("52") / Decimal("12"))
    ctx.update({
        "subscriptions": subs,
        "monthly_total": monthly_total,
    })
    return render(request, "tracker/subscription_list.html", ctx)


@login_required
def subscription_create(request):
    _ensure_defaults(request.user)
    form = SubscriptionForm(request.POST or None, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            sub = form.save(commit=False)
            sub.user = request.user
            sub.save()
            messages.success(request, f"Subscription '{sub.name}' added.")
            return redirect("subscription_list")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.capitalize()}: {err}" if field != '__all__' else err)
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title="New subscription", is_edit=False)
    return render(request, "tracker/subscription_form.html", ctx)


@login_required
def subscription_edit(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, user=request.user)
    form = SubscriptionForm(request.POST or None, instance=sub, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            messages.success(request, f"Subscription '{sub.name}' updated.")
            return redirect("subscription_list")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.capitalize()}: {err}" if field != '__all__' else err)
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title=f"Edit {sub.name}", subscription_pk=pk, is_edit=True)
    return render(request, "tracker/subscription_form.html", ctx)


@login_required
def subscription_delete(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, user=request.user)
    if request.method == "POST":
        sub.delete()
        messages.success(request, f"Subscription '{sub.name}' deleted.")
        return redirect("subscription_list")
    ctx = _sheet_context(request.user)
    ctx.update(obj=sub, back="subscription_list")
    return render(request, "tracker/confirm_delete.html", ctx)


@login_required
@require_POST
def subscription_pay(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, user=request.user)
    if sub.is_completed:
        messages.info(request, f"Subscription '{sub.name}' is already completed.")
        referer = request.META.get("HTTP_REFERER", "")
        return redirect("subscription_list" if "subscriptions" in referer else "dashboard")

    wallet = sub.wallet or Wallet.objects.filter(user=request.user, archived=False).first()
    category = sub.category or Category.objects.filter(user=request.user, kind=Category.Kind.EXPENSE).first()
    if not wallet or not category:
        messages.error(request, "Need at least one wallet and category to record transaction.")
        return redirect("subscription_list")

    note_text = f"{sub.name} payment"
    if sub.total_installments:
        current_num = (sub.already_paid_installments or 0) + sub.payments.count() + 1
        note_text = f"{sub.name} installment ({current_num}/{sub.total_installments})"

    tx = Transaction.objects.create(
        user=request.user,
        kind=Transaction.Kind.EXPENSE,
        wallet=wallet,
        category=category,
        amount=sub.amount,
        note=note_text,
        date=timezone.now(),
    )
    SubscriptionPayment.objects.create(
        subscription=sub,
        amount=sub.amount,
        wallet=wallet,
        transaction=tx,
        date=tx.date,
        note=note_text,
    )
    sub.last_paid_date = timezone.localdate()
    sub.save(update_fields=["last_paid_date"])

    if sub.is_completed:
        messages.success(request, f"Recorded final payment for {sub.name}! Subscription completed ✓")
    else:
        messages.success(request, f"Recorded payment of Rp{int(sub.amount):,} for {sub.name}! Marked as paid.")

    referer = request.META.get("HTTP_REFERER", "")
    if "subscriptions" in referer:
        return redirect("subscription_list")
    return redirect("dashboard")


@login_required
@require_POST
def subscription_undo(request, pk):
    sub = get_object_or_404(Subscription, pk=pk, user=request.user)
    payment = sub.payments.first()
    if payment:
        payment.delete()  # post_delete receiver deletes linked transaction, restoring wallet balance
        messages.success(request, f"Undid payment for {sub.name}. Wallet balance restored.")
    else:
        sub.last_paid_date = None
        sub.save(update_fields=["last_paid_date"])
        messages.success(request, f"Payment status for {sub.name} reset.")

    referer = request.META.get("HTTP_REFERER", "")
    if "subscriptions" in referer:
        return redirect("subscription_list")
    return redirect("dashboard")


@login_required
@require_POST
def subscription_payment_delete(request, pk, payment_pk):
    sub = get_object_or_404(Subscription, pk=pk, user=request.user)
    payment = get_object_or_404(SubscriptionPayment, pk=payment_pk, subscription=sub)
    payment.delete()  # cascades to transaction, syncs last_paid_date
    messages.success(request, f"Deleted payment of Rp{int(payment.amount):,} for {sub.name}.")
    referer = request.META.get("HTTP_REFERER", "")
    if "subscriptions" in referer:
        return redirect("subscription_list")
    return redirect("dashboard")


@login_required
@require_POST
def budget_set(request):
    amount_raw = request.POST.get("amount", "").strip().replace(",", "").replace(".", "")
    try:
        amount = Decimal(amount_raw)
    except Exception:
        amount = Decimal("0")

    if amount > 0:
        Budget.objects.update_or_create(
            user=request.user,
            category=None,
            defaults={"amount": amount},
        )
        messages.success(request, f"Daily budget set to Rp{int(amount):,}".replace(",", "."))
    else:
        Budget.objects.filter(user=request.user, category=None).delete()
        messages.success(request, "Daily budget removed.")
    return redirect(request.POST.get("next") or "dashboard")


@login_required
def export_csv(request):
    export_all = request.GET.get("all") == "1"
    month_str = request.GET.get("month")

    qs = Transaction.objects.filter(user=request.user).select_related("category", "wallet", "from_wallet", "to_wallet").order_by("-date", "-id")

    if not export_all and month_str:
        sel_month = _parse_month_param(month_str)
        m_start, m_end = _month_bounds(sel_month)
        qs = qs.filter(date__gte=m_start, date__lte=m_end)
        filename = f"wang_transactions_{sel_month.strftime('%Y_%m')}.csv"
    else:
        filename = f"wang_transactions_all_{timezone.localdate().strftime('%Y_%m_%d')}.csv"

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    # Write UTF-8 BOM so Excel opens cleanly without garbled characters
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(["Date", "Time", "Type", "Category", "Account", "From Account", "To Account", "Amount (IDR)", "Note", "Receipt URL"])

    for t in qs:
        local_dt = timezone.localtime(t.date) if timezone.is_aware(t.date) else t.date
        d_str = local_dt.strftime("%Y-%m-%d")
        t_str = local_dt.strftime("%H:%M")
        kind_str = t.get_kind_display()
        cat_str = t.category.name if t.category else ""
        wallet_str = t.wallet.name if t.wallet else ""
        from_str = t.from_wallet.name if t.from_wallet else ""
        to_str = t.to_wallet.name if t.to_wallet else ""
        amt_str = f"{t.amount:.2f}"
        note_str = t.note or ""
        img_str = request.build_absolute_uri(t.image.url) if t.image else ""

        writer.writerow([d_str, t_str, kind_str, cat_str, wallet_str, from_str, to_str, amt_str, note_str, img_str])

    return response


def service_worker(request):
    sw_path = os.path.join(settings.BASE_DIR, "static", "js", "sw.js")
    if os.path.exists(sw_path):
        response = FileResponse(open(sw_path, "rb"), content_type="application/javascript")
        response["Service-Worker-Allowed"] = "/"
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
    return HttpResponse("// SW not found", content_type="application/javascript", status=404)


def offline_view(request):
    ctx = {}
    if request.user.is_authenticated:
        ctx.update(_sheet_context(request.user))
    return render(request, "tracker/offline.html", ctx)


# ── Debts & Loans (Utang & Piutang) ──────────────────────────
@login_required
def debt_list(request):
    _ensure_defaults(request.user)
    tab = request.GET.get("tab", "all")  # all | lent | borrowed | settled

    all_debts = list(
        Debt.objects.filter(user=request.user)
        .select_related("wallet")
        .prefetch_related("payments__wallet")
    )

    total_lent_remaining = Decimal("0")
    total_borrowed_remaining = Decimal("0")
    active_count = 0
    settled_count = 0

    for d in all_debts:
        if d.is_settled:
            settled_count += 1
        else:
            active_count += 1
            if d.kind == Debt.Kind.LENT:
                total_lent_remaining += d.remaining_amount
            elif d.kind == Debt.Kind.BORROWED:
                total_borrowed_remaining += d.remaining_amount

    net_debt = total_lent_remaining - total_borrowed_remaining

    # Filter for display
    if tab == "lent":
        displayed_debts = [d for d in all_debts if d.kind == Debt.Kind.LENT and not d.is_settled]
    elif tab == "borrowed":
        displayed_debts = [d for d in all_debts if d.kind == Debt.Kind.BORROWED and not d.is_settled]
    elif tab == "settled":
        displayed_debts = [d for d in all_debts if d.is_settled]
    else:  # 'all'
        displayed_debts = all_debts

    wallets = Wallet.objects.filter(user=request.user, archived=False)

    ctx = _sheet_context(request.user)
    ctx.update({
        "debts": displayed_debts,
        "all_debts_count": len(all_debts),
        "total_lent_remaining": total_lent_remaining,
        "total_borrowed_remaining": total_borrowed_remaining,
        "net_debt": net_debt,
        "active_count": active_count,
        "settled_count": settled_count,
        "current_tab": tab,
        "wallets": wallets,
    })
    return render(request, "tracker/debt_list.html", ctx)


def _get_or_create_utangs_category(user, kind):
    """
    Finds or creates the 'Utangs' category for the given user and transaction kind (expense or income).
    """
    cat = Category.objects.filter(user=user, kind=kind, name__iexact="Utangs").first()
    if not cat:
        cat = Category.objects.filter(user=user, kind=kind, name__iexact="Utang").first()
    if not cat:
        default_color = "#B5EAD7" if kind == Transaction.Kind.EXPENSE else "#C7CEEA"
        cat, _ = Category.objects.get_or_create(
            user=user,
            name="Utangs",
            kind=kind,
            defaults={"icon": "handshake", "color": default_color},
        )
    return cat


def _sync_debt_origin_transaction(user, debt):
    if not debt.wallet:
        if debt.transaction:
            tx = debt.transaction
            debt.transaction = None
            debt.save(update_fields=["transaction"])
            try:
                tx.delete()
            except Exception:
                pass
        return None

    if debt.kind == Debt.Kind.LENT:
        tx_kind = Transaction.Kind.EXPENSE
        base_desc = f"Lent to {debt.person_name}"
    else:
        tx_kind = Transaction.Kind.INCOME
        base_desc = f"Borrowed from {debt.person_name}"

    tx_note = f"{base_desc} - {debt.note}" if debt.note else base_desc
    category = _get_or_create_utangs_category(user, tx_kind)

    if debt.transaction:
        tx = debt.transaction
        tx.wallet = debt.wallet
        tx.kind = tx_kind
        tx.category = category
        tx.amount = debt.amount
        tx.note = tx_note
        tx.save()
        return tx
    else:
        tx = Transaction.objects.create(
            user=user,
            kind=tx_kind,
            wallet=debt.wallet,
            category=category,
            amount=debt.amount,
            note=tx_note,
            date=timezone.now(),
        )
        debt.transaction = tx
        debt.save(update_fields=["transaction"])
        return tx


@login_required
def debt_create(request):
    _ensure_defaults(request.user)
    form = DebtForm(request.POST or None, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            debt = form.save(commit=False)
            debt.user = request.user
            debt.save()
            _sync_debt_origin_transaction(request.user, debt)
            wallet_msg = f" (synced with {debt.wallet.name})" if debt.wallet else ""
            messages.success(request, f"Debt for '{debt.person_name}' added{wallet_msg}.")
            return redirect("debt_list")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.capitalize()}: {err}" if field != '__all__' else err)
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title="New Debt/Loan", is_edit=False)
    return render(request, "tracker/debt_form.html", ctx)


@login_required
def debt_edit(request, pk):
    debt = get_object_or_404(Debt, pk=pk, user=request.user)
    form = DebtForm(request.POST or None, instance=debt, user=request.user)
    if request.method == "POST":
        if form.is_valid():
            debt = form.save()
            _sync_debt_origin_transaction(request.user, debt)
            messages.success(request, f"Debt for '{debt.person_name}' updated.")
            return redirect("debt_list")
        else:
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{field.capitalize()}: {err}" if field != '__all__' else err)
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title=f"Edit {debt.person_name}", debt_pk=pk, is_edit=True)
    return render(request, "tracker/debt_form.html", ctx)



@login_required
def debt_delete(request, pk):
    debt = get_object_or_404(Debt, pk=pk, user=request.user)
    if request.method == "POST":
        name = debt.person_name
        debt.delete()
        messages.success(request, f"Debt for '{name}' deleted.")
        return redirect("debt_list")
    ctx = _sheet_context(request.user)
    ctx.update(obj=debt, back="debt_list")
    return render(request, "tracker/confirm_delete.html", ctx)


def _create_debt_payment_transaction(user, debt, amount, wallet, note):
    if not wallet or amount <= 0:
        return None

    if debt.kind == Debt.Kind.BORROWED:
        tx_kind = Transaction.Kind.EXPENSE
        base_desc = f"Debt repayment to {debt.person_name}"
    else:
        tx_kind = Transaction.Kind.INCOME
        base_desc = f"Debt repayment from {debt.person_name}"

    tx_note = f"{base_desc} - {note}" if note else base_desc
    category = _get_or_create_utangs_category(user, tx_kind)

    return Transaction.objects.create(
        user=user,
        kind=tx_kind,
        wallet=wallet,
        category=category,
        amount=amount,
        note=tx_note,
        date=timezone.now(),
    )


@login_required
@require_POST
def debt_payment_create(request, pk):
    debt = get_object_or_404(Debt, pk=pk, user=request.user)
    amount_raw = request.POST.get("amount", "").strip().replace(",", "").replace(".", "")
    try:
        amount = Decimal(amount_raw)
    except Exception:
        amount = Decimal("0")

    if amount <= 0:
        messages.error(request, "Please enter a valid repayment amount.")
        return redirect("debt_list")

    wallet_id = request.POST.get("wallet") or None
    wallet = None
    if wallet_id:
        wallet = Wallet.objects.filter(user=request.user, pk=wallet_id).first()

    note = request.POST.get("note", "").strip()

    tx = _create_debt_payment_transaction(request.user, debt, amount, wallet, note)

    DebtPayment.objects.create(
        debt=debt,
        amount=amount,
        wallet=wallet,
        transaction=tx,
        date=timezone.now(),
        note=note,
    )
    debt.refresh_from_db()

    wallet_sync_txt = f" (synced with {wallet.name})" if wallet else ""
    status_txt = "Marked as fully settled ✓!" if debt.is_settled else f"Remaining balance: Rp{int(debt.remaining_amount):,}."
    messages.success(request, f"Recorded repayment of Rp{int(amount):,} for {debt.person_name}{wallet_sync_txt}. {status_txt}")
    referer = request.META.get("HTTP_REFERER", "")
    if referer and "debts" not in referer:
        return redirect("dashboard")
    return redirect("debt_list")


@login_required
@require_POST
def debt_settle(request, pk):
    debt = get_object_or_404(Debt, pk=pk, user=request.user)
    rem = debt.remaining_amount
    wallet = debt.wallet
    if rem > 0:
        tx = _create_debt_payment_transaction(request.user, debt, rem, wallet, "Full settlement") if wallet else None
        DebtPayment.objects.create(
            debt=debt,
            amount=rem,
            wallet=wallet,
            transaction=tx,
            date=timezone.now(),
            note="Full settlement",
        )
    debt.status = Debt.Status.SETTLED
    debt.save(update_fields=["status", "updated_at"])

    wallet_sync_txt = f" (synced with {wallet.name})" if wallet else ""
    messages.success(request, f"Debt with {debt.person_name} marked as fully settled ✓{wallet_sync_txt}!")
    referer = request.META.get("HTTP_REFERER", "")
    if referer and "debts" not in referer:
        return redirect("dashboard")
    return redirect("debt_list")


@login_required
@require_POST
def debt_payment_delete(request, pk, payment_pk):
    debt = get_object_or_404(Debt, pk=pk, user=request.user)
    payment = get_object_or_404(DebtPayment, pk=payment_pk, debt=debt)
    amount_val = payment.amount
    payment.delete()  # post_delete signal deletes linked transaction, and delete() syncs debt status
    debt.refresh_from_db()
    messages.success(request, f"Deleted payment of Rp{int(amount_val):,} for {debt.person_name}.")
    referer = request.META.get("HTTP_REFERER", "")
    if "debts" in referer:
        return redirect("debt_list")
    return redirect("dashboard")


def _get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@login_required
def more_view(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    profile = _get_or_create_profile(request.user)
    active_subs_count = Subscription.objects.filter(user=request.user, active=True).count()
    active_debts_count = Debt.objects.filter(user=request.user).exclude(status=Debt.Status.SETTLED).count()
    categories_count = Category.objects.filter(user=request.user).count()
    total_tx_count = Transaction.objects.filter(user=request.user).count()
    overall_budget = Budget.objects.filter(user=request.user, category__isnull=True).first()
    ctx.update({
        "profile": profile,
        "active_subs_count": active_subs_count,
        "active_debts_count": active_debts_count,
        "categories_count": categories_count,
        "total_tx_count": total_tx_count,
        "overall_budget": overall_budget,
    })
    return render(request, "tracker/more.html", ctx)


@login_required
def profile_edit_view(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    profile = _get_or_create_profile(request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated successfully ✨")
            return redirect("more")
    else:
        form = ProfileForm(instance=profile)

    total_tx_count = Transaction.objects.filter(user=request.user).count()
    wallets_count = Wallet.objects.filter(user=request.user, archived=False).count()

    ctx.update({
        "profile": profile,
        "form": form,
        "total_tx_count": total_tx_count,
        "wallets_count": wallets_count,
    })
    return render(request, "tracker/profile_form.html", ctx)


@require_POST
@login_required
def profile_remove_avatar(request):
    profile = _get_or_create_profile(request.user)
    if profile.avatar:
        from .image_utils import delete_file_safely
        delete_file_safely(profile.avatar)
        profile.avatar = None
        profile.save(update_fields=["avatar", "updated_at"])
        messages.success(request, "Profile photo removed.")
    return redirect("profile_edit")


@require_POST
@login_required
def api_scan_receipt(request):
    """
    Analyzes an uploaded receipt image using Google Gemini Vision API.
    Returns structured JSON with total_amount, merchant, note, suggested category, and date.
    """
    image_file = request.FILES.get("image")
    if not image_file:
        return JsonResponse({"success": False, "error": "No receipt image provided."}, status=400)

    # Fetch user's active expense categories for category matching
    categories = Category.objects.filter(user=request.user, kind="expense")
    category_map = {c.name.strip().lower(): c for c in categories}
    category_names = [c.name for c in categories]

    # Fetch user's active wallets for wallet matching
    wallets = list(Wallet.objects.filter(user=request.user, archived=False))
    wallet_options = [{"name": w.name, "type": w.type} for w in wallets]

    result = scan_receipt_with_gemini(
        image_file_or_bytes=image_file,
        category_names=category_names,
        wallet_options=wallet_options,
    )

    if not result.get("success"):
        return JsonResponse(result, status=200)

    # Match suggested category against user's categories
    suggested = (result.get("suggested_category") or "").strip().lower()
    matched_cat = None
    if suggested:
        if suggested in category_map:
            matched_cat = category_map[suggested]
        else:
            for name_lower, cat_obj in category_map.items():
                if name_lower in suggested or suggested in name_lower:
                    matched_cat = cat_obj
                    break

    # Match suggested wallet or payment method against user's wallets
    suggested_w_name = (result.get("suggested_wallet") or "").strip().lower()
    pm_raw = (result.get("payment_method") or "").strip().lower()
    matched_wallet = None

    # 1. Direct name match from AI suggested wallet
    if suggested_w_name:
        for w in wallets:
            if w.name.strip().lower() == suggested_w_name:
                matched_wallet = w
                break
        if not matched_wallet:
            for w in wallets:
                w_name_l = w.name.strip().lower()
                if suggested_w_name in w_name_l or w_name_l in suggested_w_name:
                    matched_wallet = w
                    break

    # 2. Match from payment_method string if suggested wallet didn't match
    if not matched_wallet and pm_raw:
        # Check direct wallet name substring
        for w in wallets:
            w_name_l = w.name.strip().lower()
            if w_name_l in pm_raw or pm_raw in w_name_l:
                matched_wallet = w
                break

        # Check bank names specifically
        if not matched_wallet:
            bank_keywords = ["bca", "mandiri", "bri", "bni", "cimb", "jago", "seabank", "blu", "jenius", "permata", "bsi"]
            for bkw in bank_keywords:
                if bkw in pm_raw:
                    matched_wallet = next((w for w in wallets if bkw in w.name.lower()), None)
                    if matched_wallet:
                        break

        # Check e-wallet brand names specifically
        if not matched_wallet:
            ewallet_keywords = ["gopay", "ovo", "shopeepay", "dana", "linkaja", "qris"]
            for ekw in ewallet_keywords:
                if ekw in pm_raw:
                    matched_wallet = next((w for w in wallets if ekw in w.name.lower()), None)
                    if matched_wallet:
                        break

        # Fallback to wallet type matching
        if not matched_wallet:
            if any(kw in pm_raw for kw in ["cash", "tunai", "uang pas", "kembali"]):
                matched_wallet = next((w for w in wallets if w.type == Wallet.WalletType.CASH), None)
            elif any(kw in pm_raw for kw in ["qris", "ewallet", "e-wallet", "dompet digital"]):
                matched_wallet = next((w for w in wallets if w.type == Wallet.WalletType.EWALLET), None)
            elif any(kw in pm_raw for kw in ["debit", "kartu debit", "card", "kartu kredit", "credit card", "bank", "transfer"]):
                matched_wallet = next((w for w in wallets if w.type == Wallet.WalletType.BANK), None)

    response_data = {
        "success": True,
        "total_amount": result.get("total_amount"),
        "merchant": result.get("merchant"),
        "note": result.get("note"),
        "category_id": matched_cat.id if matched_cat else None,
        "category_name": matched_cat.name if matched_cat else (result.get("suggested_category") or None),
        "wallet_id": matched_wallet.id if matched_wallet else None,
        "wallet_name": matched_wallet.name if matched_wallet else None,
        "payment_method": result.get("payment_method"),
        "discount_amount": result.get("discount_amount", 0),
        "date": result.get("date"),
    }
    return JsonResponse(response_data)


class WangLoginView(auth_views.LoginView):
    template_name = "registration/login.html"

    def form_invalid(self, form):
        if form.non_field_errors():
            error_msg = form.non_field_errors()[0]
            if "Please enter a correct username and password" in error_msg:
                error_msg = "Invalid username or password. Please try again."
        elif "username" in form.errors and "password" in form.errors:
            error_msg = "Username and password are required."
        elif "username" in form.errors:
            error_msg = "Please enter your username."
        elif "password" in form.errors:
            error_msg = "Please enter your password."
        else:
            error_msg = "Login failed. Please check your credentials and try again."

        messages.error(self.request, error_msg)
        response = super().form_invalid(form)
        response.status_code = 422
        return response





