from django import forms
from django.utils import timezone
from .models import Wallet, Category, Transaction, Subscription, Debt, DebtPayment, UserProfile


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
        fields = ["name", "amount", "wallet", "category", "cycle", "due_month", "due_day", "icon", "color", "total_installments", "already_paid_installments", "end_date", "active"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
            "due_month": forms.Select(attrs={"class": "input"}),
            "due_day": forms.NumberInput(attrs={"min": 1, "max": 31, "placeholder": "Day of month (1-31)"}),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "total_installments": forms.NumberInput(attrs={"min": 1, "placeholder": "e.g. 12 (optional)", "class": "input"}),
            "already_paid_installments": forms.NumberInput(attrs={"min": 0, "placeholder": "e.g. 2 (already paid)", "class": "input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["wallet"].queryset = Wallet.objects.filter(user=user, archived=False)
            self.fields["category"].queryset = Category.objects.filter(user=user, kind=Category.Kind.EXPENSE)
        self.fields["wallet"].required = False
        self.fields["category"].required = False
        self.fields["due_month"].required = False
        self.fields["end_date"].required = False
        self.fields["total_installments"].required = False
        self.fields["already_paid_installments"].required = False

    def clean(self):
        data = super().clean()
        cycle = data.get("cycle")
        due_month = data.get("due_month")
        if cycle == Subscription.Cycle.YEARLY and not due_month:
            from django.utils import timezone
            data["due_month"] = timezone.localdate().month
        already_paid = data.get("already_paid_installments") or 0
        total = data.get("total_installments")
        if total and already_paid > total:
            self.add_error("already_paid_installments", "Already paid installments cannot exceed total installments.")
        return data


class DebtForm(forms.ModelForm):
    class Meta:
        model = Debt
        fields = ["kind", "person_name", "amount", "wallet", "due_date", "note"]
        widgets = {
            "kind": forms.Select(attrs={"class": "input"}),
            "person_name": forms.TextInput(attrs={"placeholder": "e.g. Budi, Mom, Alice...", "class": "input"}),
            "amount": forms.NumberInput(attrs={"placeholder": "0", "step": "any", "class": "input"}),
            "due_date": forms.DateInput(attrs={"type": "date", "class": "input"}),
            "note": forms.TextInput(attrs={"placeholder": "e.g. Lunch treat, Concert ticket...", "class": "input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["wallet"].queryset = Wallet.objects.filter(user=user, archived=False)
        self.fields["wallet"].required = False
        self.fields["due_date"].required = False
        self.fields["note"].required = False


class DebtPaymentForm(forms.ModelForm):
    class Meta:
        model = DebtPayment
        fields = ["amount", "wallet", "date", "note"]
        widgets = {
            "amount": forms.NumberInput(attrs={"placeholder": "0", "step": "any", "class": "input"}),
            "date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input"}, format="%Y-%m-%dT%H:%M"),
            "note": forms.TextInput(attrs={"placeholder": "e.g. Partial transfer, Cash payment...", "class": "input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["wallet"].queryset = Wallet.objects.filter(user=user, archived=False)
        self.fields["wallet"].required = False
        self.fields["date"].required = False
        self.fields["note"].required = False

    def clean_date(self):
        d = self.cleaned_data.get("date")
        return d or timezone.now()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["display_name", "avatar", "bio", "currency_symbol"]
        widgets = {
            "display_name": forms.TextInput(attrs={"placeholder": "e.g. Raihan", "class": "input"}),
            "bio": forms.TextInput(attrs={"placeholder": "e.g. Saving for Japan 🌸", "class": "input"}),
            "currency_symbol": forms.TextInput(attrs={"placeholder": "e.g. Rp", "class": "input"}),
            "avatar": forms.FileInput(attrs={"accept": "image/*", "class": "profile-avatar-file-input", "id": "id_avatar"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_name"].required = False
        self.fields["bio"].required = False
        self.fields["avatar"].required = False
        self.fields["currency_symbol"].required = False

