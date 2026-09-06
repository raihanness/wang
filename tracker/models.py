from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class Wallet(models.Model):
    class WalletType(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank/Debit"
        EWALLET = "ewallet", "E-Wallet"
        SAVINGS = "savings", "Savings"
        OTHER = "other", "Other"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallets")
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=20, choices=WalletType.choices, default=WalletType.CASH)
    icon = models.CharField(max_length=32, default="account_balance_wallet")
    color = models.CharField(max_length=7, default="#FFB5A7")
    initial_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    archived = models.BooleanField(default=False)
    include_in_total = models.BooleanField(default=True, help_text="Include in total balance calculation")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "name"]
        unique_together = [("user", "name")]

    def __str__(self):
        return self.name

    @property
    def current_balance(self):
        if hasattr(self, "_cached_balance"):
            return self._cached_balance
        income = self.transactions.filter(kind=Transaction.Kind.INCOME).aggregate(s=models.Sum("amount"))["s"] or Decimal("0")
        expense = self.transactions.filter(kind=Transaction.Kind.EXPENSE).aggregate(s=models.Sum("amount"))["s"] or Decimal("0")
        out_transfers = self.out_transfers.aggregate(s=models.Sum("amount"))["s"] or Decimal("0")
        in_transfers = self.in_transfers.aggregate(s=models.Sum("amount"))["s"] or Decimal("0")
        return self.initial_balance + income - expense - out_transfers + in_transfers


class Category(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=60)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    icon = models.CharField(max_length=32, default="label")
    color = models.CharField(max_length=7, default="#B5EAD7")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("user", "name", "kind")]
        verbose_name_plural = "categories"

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"


class Transaction(models.Model):
    class Kind(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expense"
        TRANSFER = "transfer", "Transfer"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="transactions")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="transactions", null=True, blank=True)
    to_wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="in_transfers", null=True, blank=True)
    from_wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="out_transfers", null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    note = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="receipts/%Y/%m/", null=True, blank=True)
    date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        if self.kind == self.Kind.TRANSFER:
            return f"Transfer {self.amount} {self.from_wallet} → {self.to_wallet}"
        return f"{self.get_kind_display()} {self.amount} @ {self.wallet}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.kind == self.Kind.TRANSFER:
            if not self.from_wallet or not self.to_wallet:
                raise ValidationError("Transfer needs both from and to wallets.")
            if self.from_wallet_id == self.to_wallet_id:
                raise ValidationError("From and to wallets must differ.")
            if self.category is not None:
                raise ValidationError("Transfer must not have a category.")
        else:
            if not self.wallet:
                raise ValidationError("Income/expense needs a wallet.")
            if not self.category:
                raise ValidationError("Income/expense needs a category.")

    def save(self, *args, **kwargs):
        from tracker.image_utils import optimize_receipt_image, delete_file_safely

        # 1. Clean up old image if replaced or removed on edit
        if self.pk:
            try:
                old_tx = Transaction.objects.get(pk=self.pk)
                if old_tx.image and (not self.image or old_tx.image.name != self.image.name):
                    delete_file_safely(old_tx.image)
            except Transaction.DoesNotExist:
                pass

        # 2. Optimize newly uploaded image to WebP with auto-resizing
        if self.image:
            from django.core.files.uploadedfile import UploadedFile
            f = getattr(self.image, "file", None)
            if isinstance(f, UploadedFile) or not self.image.name.endswith(".webp"):
                optimized = optimize_receipt_image(self.image)
                if optimized and optimized != self.image:
                    self.image.save(optimized.name, optimized, save=False)

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from tracker.image_utils import delete_file_safely
        if self.image:
            delete_file_safely(self.image)
        super().delete(*args, **kwargs)


@receiver(post_delete, sender=Transaction)
def auto_delete_receipt_on_delete(sender, instance, **kwargs):
    from tracker.image_utils import delete_file_safely
    if instance.image:
        delete_file_safely(instance.image)


class Subscription(models.Model):
    class Cycle(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        YEARLY = "yearly", "Yearly"
        WEEKLY = "weekly", "Weekly"

    class Month(models.IntegerChoices):
        JAN = 1, "January"
        FEB = 2, "February"
        MAR = 3, "March"
        APR = 4, "April"
        MAY = 5, "May"
        JUN = 6, "June"
        JUL = 7, "July"
        AUG = 8, "August"
        SEP = 9, "September"
        OCT = 10, "October"
        NOV = 11, "November"
        DEC = 12, "December"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions")
    name = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    wallet = models.ForeignKey(Wallet, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscriptions")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscriptions")
    cycle = models.CharField(max_length=15, choices=Cycle.choices, default=Cycle.MONTHLY)
    due_month = models.PositiveSmallIntegerField(choices=Month.choices, null=True, blank=True, help_text="Month when due (1-12, for yearly subscriptions)")
    due_day = models.PositiveSmallIntegerField(default=1, help_text="Day of month when due (1-31)")
    icon = models.CharField(max_length=32, default="subscriptions")
    color = models.CharField(max_length=7, default="#FFB5A7")
    active = models.BooleanField(default=True)
    last_paid_date = models.DateField(null=True, blank=True, help_text="Date when this subscription was last paid")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_day", "name"]

    def __str__(self):
        return f"{self.name} (Rp{self.amount})"

    @property
    def is_paid_this_cycle(self):
        if not self.last_paid_date:
            return False
        import calendar
        from datetime import date as dt_date, timedelta
        today = timezone.localdate()

        if self.cycle == self.Cycle.YEARLY:
            return self.last_paid_date.year == today.year

        elif self.cycle == self.Cycle.WEEKLY:
            return (today - self.last_paid_date).days < 7 and self.last_paid_date >= (today - timedelta(days=today.weekday()))

        else:  # MONTHLY (default)
            if self.last_paid_date.year == today.year and self.last_paid_date.month == today.month:
                return True
            max_day = calendar.monthrange(today.year, today.month)[1]
            day = min(self.due_day, max_day)
            due_this_month = dt_date(today.year, today.month, day)
            if self.last_paid_date >= due_this_month - timedelta(days=10) and (today - self.last_paid_date).days < 32:
                return True
            return False

    @property
    def next_due_date(self):
        import calendar
        from datetime import date as dt_date, timedelta
        today = timezone.localdate()

        if self.cycle == self.Cycle.YEARLY:
            target_month = self.due_month or today.month
            target_year = today.year
            max_day = calendar.monthrange(target_year, target_month)[1]
            day = min(self.due_day, max_day)
            due_this_year = dt_date(target_year, target_month, day)

            if self.is_paid_this_cycle:
                next_year = target_year + 1
                next_max_day = calendar.monthrange(next_year, target_month)[1]
                return dt_date(next_year, target_month, min(self.due_day, next_max_day))
            else:
                return due_this_year

        elif self.cycle == self.Cycle.WEEKLY:
            weekday_target = (self.due_day - 1) % 7
            days_ahead = (weekday_target - today.weekday()) % 7
            base_date = today + timedelta(days=days_ahead)
            if self.is_paid_this_cycle:
                return base_date + timedelta(days=7) if days_ahead == 0 else base_date
            return base_date

        else:  # MONTHLY (default)
            year = today.year
            month = today.month
            max_day = calendar.monthrange(year, month)[1]
            day = min(self.due_day, max_day)
            due_this_month = dt_date(year, month, day)

            if self.is_paid_this_cycle:
                m = month + 1
                y = year
                if m > 12:
                    m = 1
                    y += 1
                next_max_day = calendar.monthrange(y, m)[1]
                next_day = min(self.due_day, next_max_day)
                return dt_date(y, m, next_day)
            else:
                return due_this_month

    @property
    def days_until_due(self):
        today = timezone.localdate()
        return (self.next_due_date - today).days

    @property
    def status_badge(self):
        today = timezone.localdate()
        if self.is_paid_this_cycle:
            next_date = self.next_due_date
            return {
                "label": f"Next {next_date.strftime('%b %d')}",
                "short_label": "Paid ✓",
                "class": "due-paid",
                "paid": True,
            }

        due = self.next_due_date
        days = (due - today).days
        if days < 0:
            overdue_days = abs(days)
            label = f"Overdue {overdue_days}d" if overdue_days > 1 else "Overdue 1d"
            return {
                "label": label,
                "short_label": label,
                "class": "due-overdue",
                "paid": False,
            }
        elif days == 0:
            return {
                "label": "Due today",
                "short_label": "Due today",
                "class": "due-today",
                "paid": False,
            }
        elif days == 1:
            return {
                "label": "Due tomorrow",
                "short_label": "Tomorrow",
                "class": "due-soon",
                "paid": False,
            }
        elif days <= 5:
            return {
                "label": f"Due in {days} days",
                "short_label": f"In {days}d",
                "class": "due-soon",
                "paid": False,
            }
        else:
            return {
                "label": f"Due {due.strftime('%b %d')}",
                "short_label": f"Due {due.strftime('%b %d')}",
                "class": "due-later",
                "paid": False,
            }


class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budgets")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name="budgets")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "category")]

    def __str__(self):
        target = self.category.name if self.category else "Overall"
        return f"{self.user.username} - {target}: Rp{self.amount}"

