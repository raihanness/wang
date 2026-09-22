from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_delete
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
    end_date = models.DateField(null=True, blank=True, help_text="Final due date or end of installment contract")
    total_installments = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Total number of installment cycles (e.g. 12)")
    already_paid_installments = models.PositiveSmallIntegerField(default=0, help_text="Installments already paid prior to tracking in this app")
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
    def is_completed(self):
        if self.total_installments:
            total_paid = (self.already_paid_installments or 0) + self.payments.count()
            if total_paid >= self.total_installments:
                return True
        if self.end_date:
            today = timezone.localdate()
            if self.is_paid_this_cycle and (self.next_due_date > self.end_date or today >= self.end_date):
                return True
        return False

    @property
    def total_paid_amount(self):
        tracked = self.payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0")
        prior = (Decimal(str(self.already_paid_installments or 0)) * self.amount)
        return prior + tracked

    @property
    def installments_progress(self):
        paid_count = (self.already_paid_installments or 0) + self.payments.count()
        if self.total_installments:
            pct = min(100, int(round((paid_count / self.total_installments) * 100))) if self.total_installments > 0 else 100
            return {
                "paid_count": paid_count,
                "total": self.total_installments,
                "percentage": pct,
                "text": f"{paid_count}/{self.total_installments} paid",
                "is_installment": True,
            }
        if self.end_date:
            return {
                "paid_count": paid_count,
                "end_date": self.end_date,
                "text": f"Ends {self.end_date.strftime('%b %d, %Y')}",
                "is_installment": True,
            }
        return None

    def sync_last_paid_date(self):
        latest = self.payments.first()
        self.last_paid_date = latest.date.date() if latest else None
        self.save(update_fields=["last_paid_date"])

    @property
    def status_badge(self):
        today = timezone.localdate()
        if self.is_completed:
            return {
                "label": "Completed",
                "short_label": "Done",
                "class": "due-paid",
                "paid": True,
                "completed": True,
            }

        if self.is_paid_this_cycle:
            next_date = self.next_due_date
            return {
                "label": f"Next {next_date.strftime('%b %d')}",
                "short_label": "Paid",
                "class": "due-paid",
                "paid": True,
                "completed": False,
            }

        due = self.next_due_date
        days = (due - today).days
        if days < 0:
            overdue_days = abs(days)
            label = f"Late {overdue_days}d" if overdue_days > 1 else "Late 1d"
            return {
                "label": label,
                "short_label": label,
                "class": "due-overdue",
                "paid": False,
                "completed": False,
            }
        elif days == 0:
            return {
                "label": "Due today",
                "short_label": "Due today",
                "class": "due-today",
                "paid": False,
                "completed": False,
            }
        elif days == 1:
            return {
                "label": "Due tomorrow",
                "short_label": "Tomorrow",
                "class": "due-soon",
                "paid": False,
                "completed": False,
            }
        elif days <= 5:
            return {
                "label": f"Due in {days} days",
                "short_label": f"In {days}d",
                "class": "due-soon",
                "paid": False,
                "completed": False,
            }
        else:
            return {
                "label": f"Due {due.strftime('%b %d')}",
                "short_label": f"Due {due.strftime('%b %d')}",
                "class": "due-later",
                "paid": False,
                "completed": False,
            }


class SubscriptionPayment(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    wallet = models.ForeignKey(Wallet, on_delete=models.SET_NULL, null=True, blank=True, related_name="subscription_payments")
    transaction = models.OneToOneField("tracker.Transaction", on_delete=models.SET_NULL, null=True, blank=True, related_name="subscription_payment")
    date = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"Payment Rp{self.amount} for {self.subscription.name}"

    def delete(self, *args, **kwargs):
        sub = self.subscription
        super().delete(*args, **kwargs)
        sub.sync_last_paid_date()


@receiver(post_delete, sender=SubscriptionPayment)
def auto_delete_transaction_on_subscription_payment_delete(sender, instance, **kwargs):
    if instance.transaction_id:
        try:
            Transaction.objects.filter(pk=instance.transaction_id).delete()
        except Exception:
            pass


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


class Debt(models.Model):
    class Kind(models.TextChoices):
        LENT = "lent", "Owed to Me"
        BORROWED = "borrowed", "I Owe"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partially Paid"
        SETTLED = "settled", "Settled"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="debts")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.BORROWED)
    person_name = models.CharField(max_length=80)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    wallet = models.ForeignKey(Wallet, on_delete=models.SET_NULL, null=True, blank=True, related_name="debts")
    transaction = models.OneToOneField("tracker.Transaction", on_delete=models.SET_NULL, null=True, blank=True, related_name="debt_origin")
    due_date = models.DateField(null=True, blank=True, help_text="Target date for full repayment")
    note = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "due_date", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.person_name} (Rp{self.amount})"

    @property
    def total_paid(self):
        return self.payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0")

    @property
    def remaining_amount(self):
        rem = self.amount - self.total_paid
        return max(Decimal("0"), rem)

    @property
    def paid_percentage(self):
        if self.amount <= 0:
            return 100
        pct = (self.total_paid / self.amount) * 100
        return min(100, int(round(pct)))

    @property
    def is_settled(self):
        return self.status == self.Status.SETTLED or self.remaining_amount <= 0

    @property
    def days_until_due(self):
        if not self.due_date:
            return None
        today = timezone.localdate()
        return (self.due_date - today).days

    @property
    def status_badge(self):
        today = timezone.localdate()
        if self.is_settled:
            return {
                "label": "Settled",
                "class": "due-paid",
                "is_settled": True,
            }

        if not self.due_date:
            if self.status == self.Status.PARTIAL:
                return {
                    "label": f"{int(self.paid_percentage)}% paid",
                    "class": "due-soon",
                    "is_settled": False,
                }
            return {
                "label": "No deadline",
                "class": "due-later",
                "is_settled": False,
            }

        days = (self.due_date - today).days
        if days < 0:
            overdue_days = abs(days)
            label = f"Late {overdue_days}d" if overdue_days > 1 else "Late 1d"
            return {
                "label": label,
                "short_label": label,
                "class": "due-overdue",
                "is_settled": False,
            }
        elif days == 0:
            return {
                "label": "Due today",
                "class": "due-today",
                "is_settled": False,
            }
        elif days == 1:
            return {
                "label": "Tomorrow",
                "class": "due-soon",
                "is_settled": False,
            }
        elif days <= 5:
            return {
                "label": f"In {days} days",
                "class": "due-soon",
                "is_settled": False,
            }
        else:
            return {
                "label": f"Due {self.due_date.strftime('%b %d')}",
                "class": "due-later",
                "is_settled": False,
            }

    def sync_status(self):
        if self.remaining_amount <= 0:
            new_status = self.Status.SETTLED
        elif self.total_paid > 0:
            new_status = self.Status.PARTIAL
        else:
            new_status = self.Status.PENDING
        if self.status != new_status:
            self.status = new_status
            self.save(update_fields=["status", "updated_at"])


class DebtPayment(models.Model):
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    wallet = models.ForeignKey(Wallet, on_delete=models.SET_NULL, null=True, blank=True, related_name="debt_payments")
    transaction = models.OneToOneField("tracker.Transaction", on_delete=models.SET_NULL, null=True, blank=True, related_name="debt_payment")
    date = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"Payment Rp{self.amount} for {self.debt}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.debt.sync_status()

    def delete(self, *args, **kwargs):
        debt = self.debt
        super().delete(*args, **kwargs)
        debt.sync_status()


@receiver(post_delete, sender=DebtPayment)
def auto_delete_transaction_on_debt_payment_delete(sender, instance, **kwargs):
    if instance.transaction_id:
        try:
            Transaction.objects.filter(pk=instance.transaction_id).delete()
        except Exception:
            pass


@receiver(post_delete, sender=Debt)
def auto_delete_transaction_on_debt_delete(sender, instance, **kwargs):
    if instance.transaction_id:
        try:
            Transaction.objects.filter(pk=instance.transaction_id).delete()
        except Exception:
            pass


# ── Bidirectional Sync: Transaction -> Payment Histories ─────────────
@receiver(post_save, sender=Transaction)
def sync_payments_on_transaction_save(sender, instance, created, **kwargs):
    if created:
        return

    # 1. Sync linked SubscriptionPayment
    try:
        sp = getattr(instance, "subscription_payment", None)
    except Exception:
        sp = None
    if sp:
        sp_changed = False
        if sp.amount != instance.amount:
            sp.amount = instance.amount
            sp_changed = True
        if sp.wallet_id != instance.wallet_id:
            sp.wallet = instance.wallet
            sp_changed = True
        if sp.date != instance.date:
            sp.date = instance.date
            sp_changed = True
        if sp.note != instance.note:
            sp.note = instance.note
            sp_changed = True
        if sp_changed:
            sp.save(update_fields=["amount", "wallet", "date", "note"])
            sp.subscription.sync_last_paid_date()

    # 2. Sync linked DebtPayment
    try:
        dp = getattr(instance, "debt_payment", None)
    except Exception:
        dp = None
    if dp:
        dp_changed = False
        if dp.amount != instance.amount:
            dp.amount = instance.amount
            dp_changed = True
        if dp.wallet_id != instance.wallet_id:
            dp.wallet = instance.wallet
            dp_changed = True
        if dp.date != instance.date:
            dp.date = instance.date
            dp_changed = True
        if dp.note != instance.note:
            dp.note = instance.note
            dp_changed = True
        if dp_changed:
            dp.save(update_fields=["amount", "wallet", "date", "note"])
            dp.debt.sync_status()

    # 3. Sync linked Debt Origin (initial loan disbursement)
    try:
        debt_origin = getattr(instance, "debt_origin", None)
    except Exception:
        debt_origin = None
    if debt_origin:
        origin_changed = False
        if debt_origin.amount != instance.amount:
            debt_origin.amount = instance.amount
            origin_changed = True
        if debt_origin.wallet_id != instance.wallet_id:
            debt_origin.wallet = instance.wallet
            origin_changed = True
        if origin_changed:
            debt_origin.save(update_fields=["amount", "wallet", "updated_at"])
            debt_origin.sync_status()


@receiver(pre_delete, sender=Transaction)
def sync_payments_on_transaction_delete(sender, instance, **kwargs):
    # 1. Delete linked SubscriptionPayment and refresh subscription cycle status
    try:
        sp = getattr(instance, "subscription_payment", None)
    except Exception:
        sp = None
    if sp:
        sp.transaction_id = None
        sp.delete()

    # 2. Delete linked DebtPayment and refresh remaining debt balance
    try:
        dp = getattr(instance, "debt_payment", None)
    except Exception:
        dp = None
    if dp:
        dp.transaction_id = None
        dp.delete()

    # 3. Detach Debt Origin if initial loan transaction is deleted
    try:
        debt_origin = getattr(instance, "debt_origin", None)
    except Exception:
        debt_origin = None
    if debt_origin:
        debt_origin.transaction = None
        debt_origin.save(update_fields=["transaction", "updated_at"])


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=60, blank=True)
    avatar = models.ImageField(upload_to="avatars/%Y/", null=True, blank=True)
    bio = models.CharField(max_length=120, blank=True)
    currency_symbol = models.CharField(max_length=10, default="Rp")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile for {self.user.username}"

    def get_display_name(self):
        return (self.display_name or "").strip() or self.user.get_full_name() or self.user.username

    def get_initials(self):
        name = self.get_display_name()
        return name[0].upper() if name else "W"

    def save(self, *args, **kwargs):
        # 1. Clean old avatar file when replaced
        if self.pk:
            try:
                orig = UserProfile.objects.filter(pk=self.pk).values("avatar").first()
                if orig and orig["avatar"] and self.avatar and orig["avatar"] != self.avatar.name:
                    import django.core.files.storage
                    storage = django.core.files.storage.default_storage
                    if storage.exists(orig["avatar"]):
                        storage.delete(orig["avatar"])
            except Exception:
                pass

        # 2. Optimize newly uploaded avatar to square WebP
        if self.avatar:
            f = getattr(self.avatar, "file", None)
            from django.core.files.uploadedfile import UploadedFile
            if isinstance(f, UploadedFile) or not self.avatar.name.endswith(".webp"):
                from .image_utils import optimize_avatar_image
                self.avatar = optimize_avatar_image(self.avatar, size=512, quality=85)

        super().save(*args, **kwargs)


@receiver(post_delete, sender=UserProfile)
def cleanup_avatar_on_profile_delete(sender, instance, **kwargs):
    if instance.avatar:
        from .image_utils import delete_file_safely
        delete_file_safely(instance.avatar)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

