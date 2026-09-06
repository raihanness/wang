from django import forms
from django.utils import timezone
from .models import Wallet, Category, Transaction, Subscription


class WalletForm(forms.ModelForm):
    class Meta:
        model = Wallet
        fields = ["name", "type", "icon", "color", "initial_balance", "include_in_total"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "icon", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ["kind", "wallet", "category", "from_wallet", "to_wallet", "amount", "note", "date", "image"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "note": forms.TextInput(attrs={"placeholder": "e.g. Lunch, Salary..."}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["wallet"].queryset = Wallet.objects.filter(user=user, archived=False)
            self.fields["from_wallet"].queryset = Wallet.objects.filter(user=user, archived=False)
            self.fields["to_wallet"].queryset = Wallet.objects.filter(user=user, archived=False)
            self.fields["category"].queryset = Category.objects.filter(user=user)
        self.fields["wallet"].required = False
        self.fields["category"].required = False
        self.fields["from_wallet"].required = False
        self.fields["to_wallet"].required = False
        self.fields["date"].required = False
        self.fields["image"].required = False

    def clean_date(self):
        d = self.cleaned_data.get("date")
        return d or timezone.now()

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        if kind == Transaction.Kind.TRANSFER:
            if not data.get("from_wallet") or not data.get("to_wallet"):
                raise forms.ValidationError("Transfer needs both wallets.")
            if data.get("from_wallet") == data.get("to_wallet"):
                raise forms.ValidationError("From and to wallets must differ.")
            data["wallet"] = None
            data["category"] = None
        else:
            if not data.get("wallet"):
                self.add_error("wallet", "Required for income/expense.")
            if not data.get("category"):
                self.add_error("category", "Required for income/expense.")
            data["from_wallet"] = None
            data["to_wallet"] = None
            cat = data.get("category")
            if cat and cat.kind != kind:
                self.add_error("category", f"Category kind is {cat.kind}, but transaction is {kind}.")
        return data


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ["name", "amount", "wallet", "category", "cycle", "due_month", "due_day", "icon", "color", "active"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
            "due_month": forms.Select(attrs={"class": "input"}),
            "due_day": forms.NumberInput(attrs={"min": 1, "max": 31, "placeholder": "Day of month (1-31)"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["wallet"].queryset = Wallet.objects.filter(user=user, archived=False)
            self.fields["category"].queryset = Category.objects.filter(user=user, kind=Category.Kind.EXPENSE)
        self.fields["wallet"].required = False
        self.fields["category"].required = False
        self.fields["due_month"].required = False

    def clean(self):
        data = super().clean()
        cycle = data.get("cycle")
        due_month = data.get("due_month")
        if cycle == Subscription.Cycle.YEARLY and not due_month:
            from django.utils import timezone
            data["due_month"] = timezone.localdate().month
        return data
