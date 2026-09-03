from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class Wallet(models.Model):
    class WalletType(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank / Debit"
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("user", "name")]

    def __str__(self):
        return self.name

    @property
    def current_balance(self):
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
        return f"{self.icon} {self.name} ({self.get_kind_display()})"


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
