from django import forms
from .models import Wallet, Category, Transaction


class WalletForm(forms.ModelForm):
    class Meta:
        model = Wallet
        fields = ["name", "type", "icon", "color", "initial_balance"]
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
        fields = ["kind", "wallet", "category", "from_wallet", "to_wallet", "amount", "note", "date"]
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
