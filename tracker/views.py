from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import timedelta, date, datetime, time
import calendar
import json

from .forms import WalletForm, CategoryForm, TransactionForm
from .models import Wallet, Category, Transaction


def _month_bounds(d):
    start = datetime(d.year, d.month, 1)
    last = calendar.monthrange(d.year, d.month)[1]
    end = datetime(d.year, d.month, last, 23, 59, 59)
    return start, end

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

def _sheet_context(user):
    """Data for the add-transaction bottom sheet (base.html includes it on every page)."""
    cats = Category.objects.filter(user=user)
    return {
        "expense_cats": cats.filter(kind=Category.Kind.EXPENSE),
        "income_cats": cats.filter(kind=Category.Kind.INCOME),
        "wallets": Wallet.objects.filter(user=user, archived=False),
    }


@login_required
def dashboard(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    wallets = ctx["wallets"]
    today = timezone.localdate()
    month_start, month_end = _month_bounds(today)

    qs_month = Transaction.objects.filter(user=request.user, date__gte=month_start, date__lte=month_end)
    income_month = qs_month.filter(kind=Transaction.Kind.INCOME).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    expense_month = qs_month.filter(kind=Transaction.Kind.EXPENSE).aggregate(s=Sum("amount"))["s"] or Decimal("0")

    total_balance = sum((w.current_balance for w in wallets), Decimal("0"))

    expense_by_cat = (
        qs_month.filter(kind=Transaction.Kind.EXPENSE)
        .values("category__name", "category__color", "category__icon")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    months = []
    now = today
    for i in range(5, -1, -1):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        d = date(y, m, 1)
        s, e = _month_bounds(d)
        inc = Transaction.objects.filter(user=request.user, kind=Transaction.Kind.INCOME, date__gte=s, date__lte=e).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        exp = Transaction.objects.filter(user=request.user, kind=Transaction.Kind.EXPENSE, date__gte=s, date__lte=e).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        months.append({"label": d.strftime("%b"), "income": float(inc), "expense": float(exp)})

    recent = Transaction.objects.filter(user=request.user).select_related("wallet", "category", "from_wallet", "to_wallet")[:10]

    month_label = today.strftime("%B %Y")
    balance_change = income_month - expense_month

    ctx.update({
        "wallets": wallets,
        "total_balance": total_balance,
        "income_month": income_month,
        "expense_month": expense_month,
        "net_month": income_month - expense_month,
        "month_label": month_label,
        "balance_change": balance_change,
        "recent": recent,
        "months_json": json.dumps(months),
        "expense_cat_json": json.dumps([{"label": r["category__name"], "value": float(r["total"]), "color": r["category__color"]} for r in expense_by_cat]),
    })
    return render(request, "tracker/dashboard.html", ctx)


@login_required
def wallet_list(request):
    _ensure_defaults(request.user)
    ctx = _sheet_context(request.user)
    ctx["wallets"] = Wallet.objects.filter(user=request.user).order_by("archived", "name")
    return render(request, "tracker/wallet_list.html", ctx)

@login_required
def wallet_create(request):
    form = WalletForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        w = form.save(commit=False)
        w.user = request.user
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
    ctx.update(form=form, title=f"Edit {w.name}")
    return render(request, "tracker/wallet_form.html", ctx)

@login_required
def wallet_toggle_archive(request, pk):
    w = get_object_or_404(Wallet, pk=pk, user=request.user)
    w.archived = not w.archived
    w.save(update_fields=["archived"])
    return redirect("wallet_list")


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
    ctx.update(form=form, title=f"Edit {c.name}", category_pk=c.pk)
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
    form = TransactionForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        t = form.save(commit=False)
        t.user = request.user
        t.save()
        messages.success(request, "Transaction added.")
        return redirect("transaction_list")
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title="New transaction")
    return render(request, "tracker/transaction_form.html", ctx)

@login_required
def transaction_edit(request, pk):
    t = get_object_or_404(Transaction, pk=pk, user=request.user)
    form = TransactionForm(request.POST or None, instance=t, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Transaction updated.")
        return redirect("transaction_list")
    ctx = _sheet_context(request.user)
    ctx.update(form=form, title="Edit transaction")
    return render(request, "tracker/transaction_form.html", ctx)

@login_required
def transaction_delete(request, pk):
    t = get_object_or_404(Transaction, pk=pk, user=request.user)
    if request.method == "POST":
        t.delete()
        messages.success(request, "Transaction deleted.")
        return redirect("transaction_list")
    ctx = _sheet_context(request.user)
    ctx.update(obj=t, back="transaction_list")
    return render(request, "tracker/confirm_delete.html", ctx)
