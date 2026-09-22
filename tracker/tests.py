from decimal import Decimal
from datetime import datetime, timedelta, date
import json
from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from tracker.models import Wallet, Category, Transaction
from tracker.views import _month_bounds


class TransactionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.client = Client()
        self.client.login(username="testuser", password="password123")

        self.wallet1 = Wallet.objects.create(
            user=self.user,
            name="Cash",
            type="cash",
            initial_balance=Decimal("100000"),
        )
        self.wallet2 = Wallet.objects.create(
            user=self.user,
            name="Bank",
            type="bank",
            initial_balance=Decimal("500000"),
        )
        self.cat_food = Category.objects.create(
            user=self.user,
            name="Food",
            kind="expense",
            icon="restaurant",
        )
        self.cat_salary = Category.objects.create(
            user=self.user,
            name="Salary",
            kind="income",
            icon="payments",
        )

    def test_add_expense_transaction(self):
        url = reverse("transaction_create")
        post_data = {
            "kind": "expense",
            "amount": "25000",
            "category": str(self.cat_food.id),
            "wallet": str(self.wallet1.id),
            "from_wallet": "",
            "to_wallet": "",
            "note": "Lunch",
            "date": "2026-09-03T12:30",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))

        tx = Transaction.objects.get(note="Lunch")
        self.assertEqual(tx.kind, "expense")
        self.assertEqual(tx.amount, Decimal("25000"))
        self.assertEqual(tx.wallet, self.wallet1)
        self.assertEqual(tx.category, self.cat_food)
        self.assertEqual(self.wallet1.current_balance, Decimal("75000"))

    def test_add_income_transaction(self):
        url = reverse("transaction_create")
        post_data = {
            "kind": "income",
            "amount": "500000",
            "category": str(self.cat_salary.id),
            "wallet": str(self.wallet2.id),
            "from_wallet": "",
            "to_wallet": "",
            "note": "Paycheck",
            "date": "2026-09-03T10:00",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))

        tx = Transaction.objects.get(note="Paycheck")
        self.assertEqual(tx.kind, "income")
        self.assertEqual(tx.amount, Decimal("500000"))
        self.assertEqual(self.wallet2.current_balance, Decimal("1000000"))

    def test_add_transfer_transaction(self):
        url = reverse("transaction_create")
        post_data = {
            "kind": "transfer",
            "amount": "50000",
            "category": "",
            "wallet": "",
            "from_wallet": str(self.wallet2.id),
            "to_wallet": str(self.wallet1.id),
            "note": "ATM withdrawal",
            "date": "2026-09-03T14:00",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))

        tx = Transaction.objects.get(note="ATM withdrawal")
        self.assertEqual(tx.kind, "transfer")
        self.assertEqual(tx.from_wallet, self.wallet2)
        self.assertEqual(tx.to_wallet, self.wallet1)
        self.assertEqual(self.wallet2.current_balance, Decimal("450000"))
        self.assertEqual(self.wallet1.current_balance, Decimal("150000"))

    def test_date_fallback_to_now(self):
        """Omitting the date should default gracefully to now instead of failing."""
        url = reverse("transaction_create")
        post_data = {
            "kind": "expense",
            "amount": "15000",
            "category": str(self.cat_food.id),
            "wallet": str(self.wallet1.id),
            "from_wallet": "",
            "to_wallet": "",
            "note": "Snack",
            "date": "",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        tx = Transaction.objects.get(note="Snack")
        self.assertIsNotNone(tx.date)

    def test_validation_missing_category_for_expense(self):
        url = reverse("transaction_create")
        post_data = {
            "kind": "expense",
            "amount": "10000",
            "category": "",
            "wallet": str(self.wallet1.id),
            "date": "2026-09-03T12:00",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Transaction.objects.filter(amount=Decimal("10000")).exists())

    def test_validation_same_wallet_transfer(self):
        url = reverse("transaction_create")
        post_data = {
            "kind": "transfer",
            "amount": "10000",
            "from_wallet": str(self.wallet1.id),
            "to_wallet": str(self.wallet1.id),
            "date": "2026-09-03T12:00",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Transaction.objects.filter(amount=Decimal("10000")).exists())

    def test_month_bounds_is_timezone_aware(self):
        d = timezone.localdate()
        start, end = _month_bounds(d)
        self.assertTrue(timezone.is_aware(start))
        self.assertTrue(timezone.is_aware(end))

    def test_transaction_edit_get_redirects_to_dashboard(self):
        tx = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("30000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Initial lunch",
        )
        url = reverse("transaction_edit", kwargs={"pk": tx.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"edit={tx.pk}", response.url)

    def test_transaction_edit_post_updates_fields(self):
        tx = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("30000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Dinner",
        )
        url = reverse("transaction_edit", kwargs={"pk": tx.pk})
        post_data = {
            "kind": "expense",
            "amount": "45000",
            "category": str(self.cat_food.id),
            "wallet": str(self.wallet1.id),
            "note": "Steak Dinner",
            "date": "2026-09-03T19:00",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))

        tx.refresh_from_db()
        self.assertEqual(tx.amount, Decimal("45000"))
        self.assertEqual(tx.note, "Steak Dinner")

    def test_dashboard_has_months_nav(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("months_nav", response.context)
        months_nav = response.context["months_nav"]
        self.assertTrue(len(months_nav) >= 6)
        active_months = [m for m in months_nav if m["is_active"]]
        self.assertEqual(len(active_months), 1)

    def test_dashboard_with_edit_param(self):
        tx = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("20000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Coffee",
        )
        response = self.client.get(f"{reverse('dashboard')}?edit={tx.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["edit_tx"], tx)

    def test_dashboard_has_tx_history_turbo_frame(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<turbo-frame id="tx-history"')
        self.assertContains(response, 'data-turbo-frame="tx-history"')

    def test_sheet_context_has_recent_notes_suggestions(self):
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("12000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Teh Pucuk Harum",
            date=timezone.now(),
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("recent_notes", response.context)
        self.assertIn("Teh Pucuk Harum", response.context["recent_notes"])
        self.assertContains(response, 'id="note-suggestions-strip"')
        self.assertContains(response, 'id="sheet-recent-notes"')
        self.assertContains(response, 'id="turbo-recent-notes"')

    def test_recent_notes_deduplication(self):
        # Multiple transactions with identical or case-differing notes
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("15000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Kopi Kenangan",
            date=timezone.now(),
        )
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("18000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Kopi Kenangan",
            date=timezone.now(),
        )
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("20000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="kopi kenangan",
            date=timezone.now(),
        )
        response = self.client.get(reverse("dashboard"))
        notes = response.context["recent_notes"]
        # Only 1 unique item should exist in recent_notes
        matching_count = len([n for n in notes if n.strip().lower() == "kopi kenangan"])
        self.assertEqual(matching_count, 1)


    def test_graphs_page_loads_with_turbo_frame_and_months_nav(self):
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("50000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=timezone.now(),
        )
        response = self.client.get(reverse("graphs"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("months_nav", response.context)
        self.assertContains(response, '<turbo-frame id="graphs-frame"')
        self.assertContains(response, 'class="month-chip')
        self.assertContains(response, 'id="pieChart"')
        self.assertContains(response, 'id="trendChart"')
        self.assertContains(response, '<script id="pie-data" type="application/json">[')

    def test_graphs_page_kind_switch(self):
        response = self.client.get(f"{reverse('graphs')}?kind=income")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["kind"], "income")
        self.assertContains(response, 'Total Income')

    def test_dashboard_has_today_summary_card(self):
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("35000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=timezone.now(),
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'today-card')
        self.assertContains(response, 'Spendable')
        self.assertEqual(response.context["today_expense"], Decimal("35000"))
        self.assertEqual(response.context["today_net"], Decimal("-35000"))

    def test_wallet_list_has_balance_card(self):
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("50000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=timezone.now(),
        )
        response = self.client.get(reverse("wallet_list"))
        self.assertContains(response, 'class="balance-card"')
        self.assertContains(response, 'hero-mode-toggle')
        self.assertContains(response, 'Expense')
        self.assertEqual(response.context["total_balance"], Decimal("550000"))  # 100k - 50k + 500k = 550k
        self.assertEqual(response.context["expense_month"], Decimal("50000"))

    def test_wallet_toggle_total_action(self):
        self.assertTrue(self.wallet1.include_in_total)
        response = self.client.get(reverse("wallet_toggle_total", args=[self.wallet1.pk]))
        self.assertRedirects(response, reverse("wallet_list"))
        self.wallet1.refresh_from_db()
        self.assertFalse(self.wallet1.include_in_total)

        # Toggle back
        response = self.client.get(reverse("wallet_toggle_total", args=[self.wallet1.pk]))
        self.assertRedirects(response, reverse("wallet_list"))
        self.wallet1.refresh_from_db()
        self.assertTrue(self.wallet1.include_in_total)

    def test_total_balance_excludes_wallet_when_toggle_off(self):
        # wallet1 balance = 100k, wallet2 balance = 500k
        # Initially both included: total = 600k
        response = self.client.get(reverse("wallet_list"))
        self.assertEqual(response.context["total_balance"], Decimal("600000"))

        # Exclude wallet1
        self.wallet1.include_in_total = False
        self.wallet1.save()

        # Now total balance should only be wallet2 = 500k
        response = self.client.get(reverse("wallet_list"))
        self.assertEqual(response.context["total_balance"], Decimal("500000"))
        self.assertContains(response, "Excluded")

        # Dashboard should also reflect 500k
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["total_balance"], Decimal("500000"))

    def test_dashboard_has_collapsible_date_groups(self):
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("15000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=timezone.now(),
        )
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<details class="day-group" open>')
        self.assertContains(response, '<summary class="day-head">')
        self.assertContains(response, 'day-chevron')

    def test_transaction_delete_post(self):
        tx = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("20000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=timezone.now(),
        )
        tx_id = tx.pk
        tx_month = timezone.localtime(tx.date).date().replace(day=1).strftime("%Y-%m")
        response = self.client.post(reverse("transaction_delete", args=[tx_id]))
        self.assertRedirects(response, f"/?month={tx_month}")
        self.assertFalse(Transaction.objects.filter(pk=tx_id).exists())

    def test_signup_disabled_redirects_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("signup"))
        self.assertRedirects(response, reverse("login"))
        # Login page itself has no signup link
        login_resp = self.client.get(reverse("login"))
        self.assertNotContains(login_resp, "Create account")

    def test_login_page_renders_redesigned_ui(self):
        self.client.logout()
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-wrap")
        self.assertContains(response, "auth-ambient-glow")
        self.assertContains(response, "auth-card")
        self.assertContains(response, "id_username")
        self.assertContains(response, "id_password")
        self.assertContains(response, "toggle-password")
        self.assertContains(response, "visibility")

    def test_base_template_has_theme_toggle_elements(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, 'id="theme-icon"')
        self.assertContains(response, 'id="meta-theme-color"')
        self.assertContains(response, 'localStorage.getItem(\'wang-theme\')')

    def test_login_invalid_credentials_shows_error_banner(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": "fakeuser", "password": "wrongpassword"})
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "auth-error-box", status_code=422)
        self.assertContains(response, "toast-error", status_code=422)
        self.assertContains(response, "Invalid username or password", status_code=422)

    def test_wallet_form_renders_visual_icon_and_color_picker(self):
        response = self.client.get(reverse("wallet_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "picker-suite")
        self.assertContains(response, "picker-preview-box")
        self.assertContains(response, "color-swatches")
        self.assertContains(response, "icon-grid-picker")
        self.assertContains(response, "id_icon")
        self.assertContains(response, "id_color")

        # Test creating wallet with picked icon and color
        post_data = {
            "name": "BCA Debit",
            "type": "bank",
            "icon": "credit_card",
            "color": "#A8D8EA",
            "initial_balance": "500000",
            "include_in_total": "on",
        }
        create_resp = self.client.post(reverse("wallet_create"), post_data)
        self.assertRedirects(create_resp, reverse("wallet_list"))
        wallet = Wallet.objects.get(user=self.user, name="BCA Debit")
        self.assertEqual(wallet.icon, "credit_card")
        self.assertEqual(wallet.color, "#A8D8EA")

    def test_category_form_renders_visual_icon_and_color_picker(self):
        response = self.client.get(reverse("category_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "picker-suite")
        self.assertContains(response, "picker-preview-box")
        self.assertContains(response, "color-swatches")
        self.assertContains(response, "icon-grid-picker")

        # Test creating category with picked icon and color
        post_data = {
            "name": "Burger Joint",
            "kind": "expense",
            "icon": "fastfood",
            "color": "#FEC8A1",
        }
        create_resp = self.client.post(reverse("category_create"), post_data)
        self.assertRedirects(create_resp, reverse("category_list"))
        cat = Category.objects.get(user=self.user, name="Burger Joint")
        self.assertEqual(cat.icon, "fastfood")
        self.assertEqual(cat.color, "#FEC8A1")

    def test_dashboard_quick_filters(self):
        # Create an expense and an income transaction
        t_exp = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("40000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Dinner",
            date=timezone.now(),
        )
        t_inc = Transaction.objects.create(
            user=self.user,
            kind="income",
            amount=Decimal("100000"),
            wallet=self.wallet1,
            category=self.cat_salary,
            note="Freelance",
            date=timezone.now(),
        )
        # 1. Filter expense
        resp_exp = self.client.get(f"{reverse('dashboard')}?filter=expense")
        self.assertEqual(resp_exp.status_code, 200)
        self.assertEqual(resp_exp.context["active_filter"], "expense")
        self.assertEqual(len(resp_exp.context["history_groups"]), 1)
        self.assertEqual(resp_exp.context["history_groups"][0][1], [t_exp])

        # 2. Filter income
        resp_inc = self.client.get(f"{reverse('dashboard')}?filter=income")
        self.assertEqual(resp_inc.status_code, 200)
        self.assertEqual(resp_inc.context["active_filter"], "income")
        self.assertEqual(len(resp_inc.context["history_groups"]), 1)
        self.assertEqual(resp_inc.context["history_groups"][0][1], [t_inc])

    def test_graphs_calculates_category_percentages(self):
        cat_snack = Category.objects.create(user=self.user, name="Snack", kind="expense", icon="cookie", color="#FFA07A")
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("75000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=timezone.now(),
        )
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("25000"),
            wallet=self.wallet1,
            category=cat_snack,
            date=timezone.now(),
        )
        resp = self.client.get(reverse("graphs"))
        self.assertEqual(resp.status_code, 200)
        by_cat = resp.context["by_cat"]
        # Total is 100,000 -> Food = 75.0%, Snack = 25.0%
        food_entry = next(r for r in by_cat if r["category__name"] == "Food")
        snack_entry = next(r for r in by_cat if r["category__name"] == "Snack")
        self.assertEqual(food_entry["pct"], 75.0)
        self.assertEqual(snack_entry["pct"], 25.0)

    def test_graphs_category_transactions_sheet_data(self):
        t1 = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("50000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Dinner with friends",
            date=timezone.now(),
        )
        t2 = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("25000"),
            wallet=self.wallet1,
            category=self.cat_food,
            note="Coffee break",
            date=timezone.now(),
        )
        resp = self.client.get(reverse("graphs"))
        self.assertEqual(resp.status_code, 200)

        # Context contains category transactions map
        self.assertIn("cat_tx_json", resp.context)
        cat_map = resp.context["cat_tx_json"]
        food_id_str = str(self.cat_food.id)
        self.assertIn(food_id_str, cat_map)
        self.assertEqual(len(cat_map[food_id_str]), 2)
        self.assertEqual(cat_map[food_id_str][0]["id"], t2.id)
        self.assertEqual(cat_map[food_id_str][1]["id"], t1.id)
        self.assertEqual(cat_map[food_id_str][0]["note"], "Coffee break")
        self.assertEqual(cat_map[food_id_str][0]["formatted_amount"], "Rp25.000")

        # Pie JSON includes id, count, and icon
        pie_json = resp.context["pie_json"]
        food_pie = next(p for p in pie_json if p["id"] == self.cat_food.id)
        self.assertEqual(food_pie["count"], 2)
        self.assertEqual(food_pie["value"], 75000.0)

        # Template contains the bottom sheet and data script
        self.assertContains(resp, 'id="cat-tx-sheet"')
        self.assertContains(resp, 'id="cat-tx-data"')

    def test_graphs_daily_average_and_projection(self):
        Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("150000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=timezone.now(),
        )
        resp = self.client.get(reverse("graphs"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("daily_avg", resp.context)
        self.assertIn("projected_total", resp.context)
        self.assertIn("peak_info", resp.context)
        self.assertGreater(resp.context["daily_avg"], Decimal("0"))
        self.assertEqual(resp.context["peak_info"]["amount"], Decimal("150000"))

    def test_subscription_crud_and_pay(self):
        from .models import Subscription
        # 1. Create subscription
        create_resp = self.client.post(reverse("subscription_create"), {
            "name": "Netflix 4K",
            "amount": "186000",
            "cycle": "monthly",
            "due_day": 15,
            "wallet": self.wallet1.pk,
            "category": self.cat_food.pk,
            "icon": "movie",
            "color": "#FFB5A7",
            "active": "on",
        })
        self.assertEqual(create_resp.status_code, 302)
        sub = Subscription.objects.get(name="Netflix 4K")
        self.assertEqual(sub.amount, Decimal("186000"))
        self.assertEqual(sub.due_day, 15)

        # 2. List subscriptions
        list_resp = self.client.get(reverse("subscription_list"))
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Netflix 4K")
        self.assertContains(list_resp, "186.000")

        # 3. Pay subscription
        self.assertFalse(sub.is_paid_this_cycle)
        pay_resp = self.client.post(reverse("subscription_pay", args=[sub.pk]))
        self.assertEqual(pay_resp.status_code, 302)
        sub.refresh_from_db()
        self.assertIsNotNone(sub.last_paid_date)
        self.assertTrue(sub.is_paid_this_cycle)
        self.assertIn("Paid", sub.status_badge["short_label"])
        self.assertEqual(sub.status_badge["class"], "due-paid")

        tx = Transaction.objects.filter(note="Netflix 4K payment").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("186000"))
        self.assertEqual(tx.kind, Transaction.Kind.EXPENSE)

        # 4. Edit subscription
        edit_resp = self.client.post(reverse("subscription_edit", args=[sub.pk]), {
            "name": "Netflix Standard",
            "amount": "120000",
            "cycle": "monthly",
            "due_day": 20,
            "wallet": self.wallet1.pk,
            "category": self.cat_food.pk,
            "icon": "movie",
            "color": "#FFB5A7",
            "active": "on",
        })
        self.assertEqual(edit_resp.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.name, "Netflix Standard")
        self.assertEqual(sub.amount, Decimal("120000"))

        # 5. Delete subscription
        del_resp = self.client.post(reverse("subscription_delete", args=[sub.pk]))
        self.assertEqual(del_resp.status_code, 302)
        self.assertFalse(Subscription.objects.filter(pk=sub.pk).exists())

    def test_subscription_paid_cycle_rollover_and_overdue(self):
        from .models import Subscription
        from datetime import timedelta
        today = timezone.localdate()

        # Monthly subscription due on the 5th
        sub_monthly = Subscription.objects.create(
            user=self.user,
            name="Spotify Premium",
            amount=Decimal("54990"),
            cycle="monthly",
            due_day=5,
            wallet=self.wallet1,
            category=self.cat_food,
            active=True,
        )

        # Before payment: not paid this cycle
        self.assertFalse(sub_monthly.is_paid_this_cycle)
        current_due = sub_monthly.next_due_date
        self.assertEqual(current_due.month, today.month)
        self.assertEqual(current_due.day, 5)

        # Mark paid for today
        sub_monthly.last_paid_date = today
        sub_monthly.save()
        self.assertTrue(sub_monthly.is_paid_this_cycle)

        # After payment: next_due_date rolls over to next month
        next_due = sub_monthly.next_due_date
        expected_month = 1 if today.month == 12 else today.month + 1
        self.assertEqual(next_due.month, expected_month)
        self.assertEqual(next_due.day, 5)
        self.assertEqual(sub_monthly.status_badge["class"], "due-paid")
        self.assertIn("Paid", sub_monthly.status_badge["short_label"])

    def test_subscription_pay_creates_payment_and_undo_reverts(self):
        from .models import Subscription, SubscriptionPayment
        initial_bal = self.wallet1.current_balance

        sub = Subscription.objects.create(
            user=self.user,
            name="Gym Membership",
            amount=Decimal("300000"),
            cycle="monthly",
            due_day=10,
            wallet=self.wallet1,
            category=self.cat_food,
            active=True,
        )

        # Pay subscription
        pay_resp = self.client.post(reverse("subscription_pay", args=[sub.pk]))
        self.assertEqual(pay_resp.status_code, 302)
        sub.refresh_from_db()
        self.assertTrue(sub.is_paid_this_cycle)
        self.assertEqual(sub.payments.count(), 1)
        pmt = sub.payments.first()
        self.assertIsNotNone(pmt.transaction)
        self.assertEqual(self.wallet1.current_balance, initial_bal - Decimal("300000"))

        # Undo payment
        undo_resp = self.client.post(reverse("subscription_undo", args=[sub.pk]))
        self.assertEqual(undo_resp.status_code, 302)
        sub.refresh_from_db()
        self.assertFalse(sub.is_paid_this_cycle)
        self.assertIsNone(sub.last_paid_date)
        self.assertEqual(sub.payments.count(), 0)
        self.assertFalse(Transaction.objects.filter(pk=pmt.transaction_id).exists())
        self.assertEqual(self.wallet1.current_balance, initial_bal)

    def test_subscription_installments_and_completion(self):
        from .models import Subscription
        sub = Subscription.objects.create(
            user=self.user,
            name="Phone Installment",
            amount=Decimal("500000"),
            cycle="monthly",
            due_day=1,
            wallet=self.wallet1,
            category=self.cat_food,
            total_installments=2,
            active=True,
        )
        self.assertEqual(sub.installments_progress["text"], "0/2 paid")
        self.assertFalse(sub.is_completed)

        # Pay 1st installment
        self.client.post(reverse("subscription_pay", args=[sub.pk]))
        sub.refresh_from_db()
        self.assertEqual(sub.installments_progress["text"], "1/2 paid")
        self.assertFalse(sub.is_completed)

        # Pay 2nd installment
        self.client.post(reverse("subscription_pay", args=[sub.pk]))
        sub.refresh_from_db()
        self.assertEqual(sub.installments_progress["text"], "2/2 paid")
        self.assertTrue(sub.is_completed)
        self.assertEqual(sub.status_badge["label"], "Completed")

        # Undo 2nd installment
        self.client.post(reverse("subscription_undo", args=[sub.pk]))
        sub.refresh_from_db()
        self.assertFalse(sub.is_completed)
        self.assertEqual(sub.installments_progress["text"], "1/2 paid")

    def test_subscription_already_paid_installments(self):
        from .models import Subscription
        # 12-month installment, 2 already paid prior to Wang
        sub = Subscription.objects.create(
            user=self.user,
            name="A07 Adul Installment",
            amount=Decimal("85000"),
            cycle="monthly",
            due_day=12,
            wallet=self.wallet1,
            category=self.cat_food,
            total_installments=12,
            already_paid_installments=2,
            active=True,
        )
        self.assertEqual(sub.installments_progress["text"], "2/12 paid")
        self.assertEqual(sub.installments_progress["percentage"], 17)
        self.assertEqual(sub.total_paid_amount, Decimal("170000"))
        self.assertFalse(sub.is_completed)

        # Pay 3rd installment via 1-tap in Wang
        resp = self.client.post(reverse("subscription_pay", args=[sub.pk]))
        self.assertEqual(resp.status_code, 302)
        sub.refresh_from_db()
        self.assertEqual(sub.installments_progress["text"], "3/12 paid")
        self.assertEqual(sub.payments.count(), 1)
        self.assertEqual(sub.total_paid_amount, Decimal("255000"))

        # Check generated transaction note
        pmt = sub.payments.first()
        self.assertEqual(pmt.note, "A07 Adul Installment installment (3/12)")
        self.assertFalse(sub.is_completed)

        # Form validation: already_paid cannot exceed total_installments
        from .forms import SubscriptionForm
        form = SubscriptionForm(
            data={
                "name": "Test Form",
                "amount": "10000",
                "cycle": "monthly",
                "due_day": 1,
                "total_installments": 5,
                "already_paid_installments": 6,
            },
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("already_paid_installments", form.errors)

    def test_transaction_with_image_upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        # 1x1 transparent GIF
        gif = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
        img_file = SimpleUploadedFile("receipt.gif", gif, content_type="image/gif")

        resp = self.client.post(reverse("transaction_create"), {
            "kind": "expense",
            "amount": "55000",
            "wallet": self.wallet1.pk,
            "category": self.cat_food.pk,
            "note": "Lunch with receipt",
            "image": img_file,
        })
        self.assertEqual(resp.status_code, 302)
        tx = Transaction.objects.get(note="Lunch with receipt")
        self.assertTrue(bool(tx.image))
        self.assertIn("receipt", tx.image.name)
        self.assertTrue(tx.image.name.endswith(".webp"))
        tx.delete()

    def test_receipt_webp_resizing_and_lifecycle_cleanup(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        # 1. Create a large 2000x1500 JPEG receipt
        raw_img = Image.new("RGB", (2000, 1500), color="purple")
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG")
        buf.seek(0)
        jpeg_upload = SimpleUploadedFile("dinner_receipt.jpg", buf.getvalue(), content_type="image/jpeg")

        resp = self.client.post(reverse("transaction_create"), {
            "kind": "expense",
            "amount": "85000",
            "wallet": self.wallet1.pk,
            "category": self.cat_food.pk,
            "note": "Big dinner",
            "image": jpeg_upload,
        })
        self.assertEqual(resp.status_code, 302)

        tx = Transaction.objects.get(note="Big dinner")
        self.assertTrue(bool(tx.image))
        self.assertTrue(tx.image.name.endswith(".webp"))
        self.assertTrue(tx.image.storage.exists(tx.image.name))

        # Verify image was resized to <= 1200 max dimension
        with Image.open(tx.image.path) as saved_img:
            self.assertEqual(saved_img.format, "WEBP")
            self.assertLessEqual(max(saved_img.size), 1200)
            self.assertEqual(saved_img.size, (1200, 900))

        first_image_path = tx.image.name
        first_storage = tx.image.storage

        # 2. Replace attachment on edit
        new_img = Image.new("RGB", (800, 600), color="orange")
        new_buf = io.BytesIO()
        new_img.save(new_buf, format="PNG")
        new_buf.seek(0)
        png_upload = SimpleUploadedFile("updated_receipt.png", new_buf.getvalue(), content_type="image/png")

        edit_resp = self.client.post(reverse("transaction_edit", args=[tx.pk]), {
            "kind": "expense",
            "amount": "90000",
            "wallet": self.wallet1.pk,
            "category": self.cat_food.pk,
            "note": "Big dinner updated",
            "image": png_upload,
        })
        self.assertEqual(edit_resp.status_code, 302)

        tx.refresh_from_db()
        self.assertTrue(tx.image.name.endswith(".webp"))
        self.assertIn("updated_receipt", tx.image.name)
        # Old image file MUST be deleted from disk
        self.assertFalse(first_storage.exists(first_image_path))
        # New image file MUST exist
        self.assertTrue(tx.image.storage.exists(tx.image.name))

        second_image_path = tx.image.name

        # 3. Clear attachment on edit via image_clear=1
        clear_resp = self.client.post(reverse("transaction_edit", args=[tx.pk]), {
            "kind": "expense",
            "amount": "90000",
            "wallet": self.wallet1.pk,
            "category": self.cat_food.pk,
            "note": "Big dinner updated",
            "image_clear": "1",
        })
        self.assertEqual(clear_resp.status_code, 302)

        tx.refresh_from_db()
        self.assertFalse(bool(tx.image))
        # Second image file MUST be deleted from disk
        self.assertFalse(first_storage.exists(second_image_path))

        # 4. Attach new image and test deletion of transaction
        final_img = Image.new("RGB", (400, 400), color="cyan")
        final_buf = io.BytesIO()
        final_img.save(final_buf, format="JPEG")
        final_buf.seek(0)
        final_upload = SimpleUploadedFile("final_receipt.jpg", final_buf.getvalue(), content_type="image/jpeg")

        self.client.post(reverse("transaction_edit", args=[tx.pk]), {
            "kind": "expense",
            "amount": "90000",
            "wallet": self.wallet1.pk,
            "category": self.cat_food.pk,
            "note": "Big dinner updated",
            "image": final_upload,
        })
        tx.refresh_from_db()
        final_path = tx.image.name
        self.assertTrue(first_storage.exists(final_path))

        # Delete transaction
        del_resp = self.client.post(reverse("transaction_delete", args=[tx.pk]))
        self.assertEqual(del_resp.status_code, 302)
        # File MUST be deleted from disk after transaction is deleted
        self.assertFalse(first_storage.exists(final_path))

    def test_yearly_subscription_due_month_and_overflow(self):
        from .models import Subscription
        # Create yearly subscription with due_month = 11 (November), due_day = 25
        sub = Subscription.objects.create(
            user=self.user,
            name="Super Ultra Long Subscription Name That Would Otherwise Overflow The Mobile Card Layout Screen",
            amount=Decimal("1200000"),
            cycle="yearly",
            due_month=11,
            due_day=25,
            wallet=self.wallet1,
            category=self.cat_food,
            icon="card_membership",
            color="#A8DADC",
            active=True,
        )
        # Verify next_due_date calculation
        today = timezone.localdate()
        due = sub.next_due_date
        self.assertEqual(due.month, 11)
        self.assertEqual(due.day, 25)
        self.assertGreaterEqual(due, today)

        # Verify subscription_list renders month and handles long name
        resp = self.client.get(reverse("subscription_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Nov 25th")
        self.assertContains(resp, "Super Ultra Long Subscription Name")
        # monthly_total should include prorated 1,200,000 / 12 = 100,000
        self.assertEqual(resp.context["monthly_total"], Decimal("100000"))

    def test_wallet_manual_reordering(self):
        # Initial wallets created in setUp:
        # self.wallet1 is "Cash", self.wallet2 is "Bank"
        w_gopay = Wallet.objects.create(
            user=self.user,
            name="GoPay",
            type="ewallet",
            initial_balance=Decimal("50000"),
            order=2,
        )
        self.wallet1.order = 1
        self.wallet1.save()
        self.wallet2.order = 0
        self.wallet2.save()

        # Check default ordering by order
        wallets = list(Wallet.objects.filter(user=self.user))
        self.assertEqual([w.name for w in wallets], ["Bank", "Cash", "GoPay"])

        # Reorder via POST endpoint: Put GoPay first, then Cash, then Bank
        resp = self.client.post(
            reverse("wallet_reorder"),
            data=json.dumps({"order": [w_gopay.pk, self.wallet1.pk, self.wallet2.pk]}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

        # Reload from db
        self.wallet1.refresh_from_db()
        self.wallet2.refresh_from_db()
        w_gopay.refresh_from_db()
        self.assertEqual(w_gopay.order, 0)
        self.assertEqual(self.wallet1.order, 1)
        self.assertEqual(self.wallet2.order, 2)

        # Verify wallet_list reflects this custom order
        list_resp = self.client.get(reverse("wallet_list"))
        self.assertEqual(list_resp.status_code, 200)
        wallets_in_list = list(list_resp.context["wallets"])
        self.assertEqual([w.name for w in wallets_in_list], ["GoPay", "Cash", "Bank"])

        # Verify _sheet_context (used in adding/editing transactions) reflects this custom order
        from tracker.views import _sheet_context
        sheet_ctx = _sheet_context(self.user)
        self.assertEqual([w.name for w in sheet_ctx["wallets"]], ["GoPay", "Cash", "Bank"])

    def test_month_popover_navigation(self):
        # 1. GET current dashboard
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'id="c-month-trigger"')
        self.assertContains(resp, 'id="month-popover"')
        self.assertContains(resp, 'id="m-year-display"')
        self.assertContains(resp, 'id="month-popover-grid"')
        self.assertContains(resp, 'class="m-popover-today-btn"')

        # 2. GET a specific older month (e.g. 2026-01)
        resp_jan = self.client.get(reverse("dashboard") + "?month=2026-01")
        self.assertEqual(resp_jan.status_code, 200)
        self.assertContains(resp_jan, "Jan 2026")
        self.assertEqual(resp_jan.context["view_month"].strftime("%Y-%m"), "2026-01")

        # 3. GET with search query and filter - popover links should preserve them
        resp_filtered = self.client.get(reverse("dashboard") + "?month=2026-01&filter=expense&q=lunch")
        self.assertEqual(resp_filtered.status_code, 200)
        self.assertContains(resp_filtered, 'filter=expense')
        self.assertContains(resp_filtered, 'q=lunch')

        # 4. Verify disabled state for months with no data vs enabled for months with data
        # In setUp, no transactions were created in 2026-02
        popover_months = resp.context["popover_months"]
        feb_entry = next(pm for pm in popover_months if pm["num"] == "02")
        self.assertFalse(feb_entry["has_data"])
        # Should render as disabled span in the HTML
        self.assertContains(resp, 'data-m="02"\n                  aria-disabled="true"\n                  title="No transactions"')

        # Add transaction in 2026-03 and verify 2026-03 becomes enabled
        Transaction.objects.create(
            user=self.user,
            wallet=self.wallet1,
            category=self.cat_food,
            amount=Decimal("15000"),
            date=timezone.make_aware(datetime(2026, 3, 10, 12, 0)),
            kind="expense",
        )
        resp_with_tx = self.client.get(reverse("dashboard"))
        popover_with_tx = resp_with_tx.context["popover_months"]
        mar_entry = next(pm for pm in popover_with_tx if pm["num"] == "03")
        self.assertTrue(mar_entry["has_data"])
        self.assertIn("2026-03", resp_with_tx.context["available_months"])

    def test_frequent_categories_ordering(self):
        """Frequently used categories should appear first in _sheet_context."""
        cat_transport = Category.objects.create(user=self.user, name="Transport", kind="expense", icon="directions_bus")
        cat_coffee = Category.objects.create(user=self.user, name="Coffee", kind="expense", icon="local_cafe")
        cat_shopping = Category.objects.create(user=self.user, name="Shopping", kind="expense", icon="shopping_bag")

        # 4 txs for Coffee, 2 txs for Transport, 1 tx for Food, 0 for Shopping
        for i in range(4):
            Transaction.objects.create(user=self.user, wallet=self.wallet1, category=cat_coffee, amount=Decimal("20000"), kind="expense")
        for i in range(2):
            Transaction.objects.create(user=self.user, wallet=self.wallet1, category=cat_transport, amount=Decimal("15000"), kind="expense")
        Transaction.objects.create(user=self.user, wallet=self.wallet1, category=self.cat_food, amount=Decimal("30000"), kind="expense")

        from tracker.views import _sheet_context
        sheet_ctx = _sheet_context(self.user)
        expense_names = [c.name for c in sheet_ctx["expense_cats"]]
        # Should be ordered by frequency: Coffee (4), Transport (2), Food (1), Shopping (0)
        self.assertEqual(expense_names[:4], ["Coffee", "Transport", "Food", "Shopping"])

    def test_graphs_monthly_dual_cashflow(self):
        """Monthly graphs view returns dual income vs expense trend and averages."""
        now = timezone.now()
        Transaction.objects.create(user=self.user, wallet=self.wallet1, category=self.cat_salary, amount=Decimal("1000000"), date=now, kind="income")
        Transaction.objects.create(user=self.user, wallet=self.wallet1, category=self.cat_food, amount=Decimal("250000"), date=now, kind="expense")

        resp = self.client.get(reverse("graphs") + "?mode=month")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["mode"], "month")
        self.assertIn("avg_6m_income", resp.context)
        self.assertIn("avg_6m_expense", resp.context)
        self.assertIn("avg_6m_net", resp.context)
        self.assertContains(resp, '6-Month Cashflow')
        self.assertContains(resp, 'id="trendChart"')

    def test_graphs_annual_year_in_review(self):
        """Annual graphs view returns full year summary, 12-month trend, and top categories."""
        now = timezone.now()
        Transaction.objects.create(user=self.user, wallet=self.wallet1, category=self.cat_salary, amount=Decimal("12000000"), date=now, kind="income")
        Transaction.objects.create(user=self.user, wallet=self.wallet1, category=self.cat_food, amount=Decimal("3000000"), date=now, kind="expense")

        resp = self.client.get(reverse("graphs") + f"?mode=year&year={now.year}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["mode"], "year")
        self.assertEqual(resp.context["annual_income"], Decimal("12000000"))
        self.assertEqual(resp.context["annual_expense"], Decimal("3000000"))
        self.assertEqual(resp.context["annual_net"], Decimal("9000000"))
        self.assertEqual(resp.context["annual_savings_rate"], 75.0)
        self.assertEqual(len(resp.context["top_3_cats"]), 1)
        self.assertEqual(resp.context["top_3_cats"][0]["category__name"], "Food")
        self.assertEqual(len(resp.context["year_trend_json"]), 12)
        self.assertContains(resp, f'{now.year} Year-in-Review')
        self.assertContains(resp, 'id="annualChart"')

    def test_service_worker_and_offline_page(self):
        """Service worker script and offline page load with expected status and headers."""
        sw_resp = self.client.get(reverse("service_worker"))
        self.assertEqual(sw_resp.status_code, 200)
        self.assertIn("application/javascript", sw_resp.headers.get("Content-Type", ""))
        self.assertEqual(sw_resp.headers.get("Service-Worker-Allowed"), "/")
        self.assertIn("no-cache", sw_resp.headers.get("Cache-Control", ""))

        offline_resp = self.client.get(reverse("offline"))
        self.assertEqual(offline_resp.status_code, 200)
        self.assertContains(offline_resp, "You're Offline")
        self.assertContains(offline_resp, "Try Reconnecting")

    def test_dashboard_multi_filters(self):
        """Dashboard filters by wallet, category, and date range in addition to type."""
        now = timezone.now()
        t1 = Transaction.objects.create(
            user=self.user, wallet=self.wallet1, category=self.cat_food,
            amount=Decimal("50000"), date=now, kind=Transaction.Kind.EXPENSE, note="Lunch at cafe"
        )
        t2 = Transaction.objects.create(
            user=self.user, wallet=self.wallet2, category=self.cat_salary,
            amount=Decimal("2000000"), date=now, kind=Transaction.Kind.INCOME, note="Freelance"
        )
        t3 = Transaction.objects.create(
            user=self.user, from_wallet=self.wallet1, to_wallet=self.wallet2,
            amount=Decimal("100000"), date=now, kind=Transaction.Kind.TRANSFER, note="Savings transfer"
        )

        # Filter by wallet
        resp_w = self.client.get(reverse("dashboard") + f"?wallet={self.wallet2.pk}")
        self.assertEqual(resp_w.status_code, 200)
        tx_ids_w = [t.id for _, items, _, _ in resp_w.context["history_groups"] for t in items]
        self.assertIn(t2.id, tx_ids_w)
        self.assertIn(t3.id, tx_ids_w)
        self.assertNotIn(t1.id, tx_ids_w)
        self.assertEqual(resp_w.context["active_filter_count"], 1)
        self.assertEqual(resp_w.context["active_filter_tags"][0]["key"], "wallet")

        # Filter by category
        resp_c = self.client.get(reverse("dashboard") + f"?category={self.cat_food.pk}")
        self.assertEqual(resp_c.status_code, 200)
        tx_ids_c = [t.id for _, items, _, _ in resp_c.context["history_groups"] for t in items]
        self.assertEqual(tx_ids_c, [t1.id])
        self.assertEqual(resp_c.context["active_filter_count"], 1)
        self.assertEqual(resp_c.context["active_filter_tags"][0]["key"], "category")

        # Filter by date range
        d_str = now.strftime("%Y-%m-%d")
        resp_d = self.client.get(reverse("dashboard") + f"?date_from={d_str}&date_to={d_str}")
        self.assertEqual(resp_d.status_code, 200)
        self.assertTrue(resp_d.context["custom_dates"])
        self.assertEqual(resp_d.context["active_filter_count"], 1)

        # Multi-filter combination: wallet + category + filter
        resp_combo = self.client.get(reverse("dashboard") + f"?wallet={self.wallet1.pk}&category={self.cat_food.pk}&filter=expense")
        self.assertEqual(resp_combo.status_code, 200)
        self.assertEqual(resp_combo.context["active_filter_count"], 3)
        self.assertContains(resp_combo, "filter-btn-trigger")
        self.assertContains(resp_combo, "active-filter-strip")

    def test_dashboard_filter_exclusions_and_multi_selection(self):
        """Dashboard supports excluding transaction types, wallets, and categories."""
        now = timezone.now()
        t_exp = Transaction.objects.create(
            user=self.user, wallet=self.wallet1, category=self.cat_food,
            amount=Decimal("50000"), date=now, kind=Transaction.Kind.EXPENSE, note="Lunch"
        )
        t_inc = Transaction.objects.create(
            user=self.user, wallet=self.wallet2, category=self.cat_salary,
            amount=Decimal("2000000"), date=now, kind=Transaction.Kind.INCOME, note="Freelance"
        )
        t_trf = Transaction.objects.create(
            user=self.user, from_wallet=self.wallet1, to_wallet=self.wallet2,
            amount=Decimal("100000"), date=now, kind=Transaction.Kind.TRANSFER, note="Transfer"
        )

        # Exclude transfer
        resp_exc = self.client.get(reverse("dashboard") + "?filter_exclude=transfer")
        self.assertEqual(resp_exc.status_code, 200)
        tx_ids = [t.id for _, items, _, _ in resp_exc.context["history_groups"] for t in items]
        self.assertIn(t_exp.id, tx_ids)
        self.assertIn(t_inc.id, tx_ids)
        self.assertNotIn(t_trf.id, tx_ids)
        self.assertEqual(resp_exc.context["active_filter_count"], 1)
        self.assertTrue(resp_exc.context["active_filter_tags"][0]["is_exclude"])

        # Multiple inclusions: expense and income
        resp_multi = self.client.get(reverse("dashboard") + "?filter=expense,income")
        self.assertEqual(resp_multi.status_code, 200)
        tx_ids_multi = [t.id for _, items, _, _ in resp_multi.context["history_groups"] for t in items]
        self.assertIn(t_exp.id, tx_ids_multi)
        self.assertIn(t_inc.id, tx_ids_multi)
        self.assertNotIn(t_trf.id, tx_ids_multi)
        self.assertEqual(resp_multi.context["active_filter_count"], 2)

        # Exclude category
        resp_exc_cat = self.client.get(reverse("dashboard") + f"?category_exclude={self.cat_food.pk}")
        self.assertEqual(resp_exc_cat.status_code, 200)
        tx_ids_cat = [t.id for _, items, _, _ in resp_exc_cat.context["history_groups"] for t in items]
        self.assertNotIn(t_exp.id, tx_ids_cat)
        self.assertIn(t_inc.id, tx_ids_cat)
        self.assertIn(t_trf.id, tx_ids_cat)

    def test_net_worth_growth_curve(self):
        """Graphs view computes net worth points and growth rate for both monthly and annual views."""
        now = timezone.now()
        Transaction.objects.create(
            user=self.user, wallet=self.wallet1, category=self.cat_salary,
            amount=Decimal("5000000"), date=now, kind=Transaction.Kind.INCOME
        )
        Transaction.objects.create(
            user=self.user, wallet=self.wallet1, category=self.cat_food,
            amount=Decimal("1500000"), date=now, kind=Transaction.Kind.EXPENSE
        )

        # Monthly mode
        resp_m = self.client.get(reverse("graphs") + "?mode=month")
        self.assertEqual(resp_m.status_code, 200)
        self.assertIn("net_worth_points", resp_m.context)
        self.assertIn("net_worth_growth_amt", resp_m.context)
        self.assertIn("net_worth_growth_pct", resp_m.context)
        self.assertContains(resp_m, "Net Worth Progression")
        self.assertContains(resp_m, 'id="netWorthChart"')

        # Annual mode
        resp_y = self.client.get(reverse("graphs") + f"?mode=year&year={now.year}")
        self.assertEqual(resp_y.status_code, 200)
        self.assertIn("net_worth_points", resp_y.context)
        self.assertContains(resp_y, 'id="netWorthChartAnnual"')

    def test_month_over_month_category_trend(self):
        """Graphs monthly view computes MoM category comparisons (diff, pct_change, trend_dir, is_new)."""
        now = timezone.now()
        cur_m = now.replace(day=15)
        # Previous month:
        prev_m = (cur_m.replace(day=1) - timedelta(days=1)).replace(day=15)

        # Last month: Food = 100,000
        Transaction.objects.create(
            user=self.user, wallet=self.wallet1, category=self.cat_food,
            amount=Decimal("100000"), date=prev_m, kind=Transaction.Kind.EXPENSE
        )

        # This month: Food = 150,000 (+50% increase), Coffee = 30,000 (New)
        cat_coffee = Category.objects.create(user=self.user, name="Coffee", kind="expense", icon="coffee", color="#FEC8A1")
        Transaction.objects.create(
            user=self.user, wallet=self.wallet1, category=self.cat_food,
            amount=Decimal("150000"), date=cur_m, kind=Transaction.Kind.EXPENSE
        )
        Transaction.objects.create(
            user=self.user, wallet=self.wallet1, category=cat_coffee,
            amount=Decimal("30000"), date=cur_m, kind=Transaction.Kind.EXPENSE
        )

        m_param = cur_m.strftime("%Y-%m")
        resp = self.client.get(reverse("graphs") + f"?mode=month&month={m_param}&kind=expense")
        self.assertEqual(resp.status_code, 200)

        by_cat = {r["category__name"]: r for r in resp.context["by_cat"]}
        self.assertIn("Food", by_cat)
        self.assertIn("Coffee", by_cat)

        food_item = by_cat["Food"]
        self.assertEqual(food_item["prev_total"], Decimal("100000"))
        self.assertEqual(food_item["diff"], Decimal("50000"))
        self.assertEqual(food_item["pct_change"], 50.0)
        self.assertEqual(food_item["trend_dir"], "up")
        self.assertFalse(food_item["is_new"])

        coffee_item = by_cat["Coffee"]
        self.assertEqual(coffee_item["prev_total"], Decimal("0"))
        self.assertTrue(coffee_item["is_new"])
        self.assertEqual(coffee_item["trend_dir"], "new")

    def test_self_hosted_fonts_and_service_worker(self):
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Ensure zero external Google Fonts CDN links (GDPR compliant)
        self.assertNotContains(resp, "fonts.googleapis.com")
        self.assertNotContains(resp, "fonts.gstatic.com")
        # Ensure local typography font preloads are present
        self.assertContains(resp, "static/fonts/plus-jakarta-sans-latin.woff2")
        # Ensure heavy 5.3MB icon font is no longer preloaded in HTML
        self.assertNotContains(resp, "static/fonts/material-symbols-rounded.woff2")

        # Verify static font serving via WhiteNoise
        resp_font = self.client.get("/static/fonts/plus-jakarta-sans-latin.woff2")
        self.assertEqual(resp_font.status_code, 200)
        self.assertEqual(resp_font.headers.get("Content-Type"), "font/woff2")

        # Verify SVG sprite sheet presence and vector symbols
        self.assertContains(resp, 'id="wang-svg-sprite"')
        self.assertContains(resp, 'id="icon-home"')
        self.assertContains(resp, 'id="icon-account_balance_wallet"')
        self.assertContains(resp, 'id="icon-restaurant"')

        resp_sw = self.client.get(reverse("service_worker"))
        self.assertEqual(resp_sw.status_code, 200)
        self.assertEqual(resp_sw.headers.get("Service-Worker-Allowed"), "/")

        # Verify vector icon CSS rules
        resp_css = self.client.get("/static/css/wang.css")
        self.assertContains(resp_css, "fill: currentColor")

    def test_early_morning_timezone_grouping(self):
        """Transactions between 00:00 and 06:59 WIB (UTC+7) must group under their local day, not the previous day."""
        import zoneinfo
        tz_jkt = zoneinfo.ZoneInfo("Asia/Jakarta")
        # 02:30 AM on Sep 6 in Jakarta = 19:30 UTC on Sep 5
        early_morning_dt = timezone.make_aware(datetime(2026, 9, 6, 2, 30, 0), tz_jkt)

        tx = Transaction.objects.create(
            user=self.user,
            kind="expense",
            amount=Decimal("35000"),
            wallet=self.wallet1,
            category=self.cat_food,
            date=early_morning_dt,
            note="Early morning breakfast",
        )

        resp = self.client.get(reverse("dashboard") + "?month=2026-09")
        self.assertEqual(resp.status_code, 200)

        groups = resp.context["history_groups"]
        self.assertTrue(len(groups) >= 1)
        group_days = [day for day, items, _, _ in groups]

        # Must be grouped as September 6, NOT September 5
        expected_local_date = date(2026, 9, 6)
        self.assertIn(expected_local_date, group_days)

        # Template must display Sunday, Sep 6
        self.assertContains(resp, "Sunday, Sep 6")

    def test_wallet_balances_api(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("api_wallets"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("wallets", data)
        wallet_names = [w["name"] for w in data["wallets"]]
        self.assertIn("Cash", wallet_names)
        self.assertIn("Bank", wallet_names)
        for w in data["wallets"]:
            self.assertTrue(w["formatted_balance"].startswith("Rp") or w["formatted_balance"].startswith("-Rp"))
            self.assertIn("id", w)
            self.assertIn("icon", w)
            self.assertIn("color", w)

    def test_wallet_delete_confirm_page(self):
        self.client.force_login(self.user)
        # Create extra wallet so user has 3 wallets
        extra_w = Wallet.objects.create(user=self.user, name="Savings", type="savings")
        url = reverse("wallet_delete", kwargs={"pk": extra_w.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Delete <strong>Savings</strong>?")
        self.assertContains(resp, reverse("wallet_list"))

    def test_wallet_delete_warning_with_transactions(self):
        self.client.force_login(self.user)
        extra_w = Wallet.objects.create(user=self.user, name="E-Wallet", type="ewallet")
        Transaction.objects.create(
            user=self.user,
            kind=Transaction.Kind.EXPENSE,
            amount=Decimal("15000"),
            wallet=extra_w,
            category=self.cat_food,
            note="Snack",
        )
        url = reverse("wallet_delete", kwargs={"pk": extra_w.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Warning: Deleting this wallet will also permanently delete 1 associated transaction.")

    def test_wallet_delete_success(self):
        self.client.force_login(self.user)
        extra_w = Wallet.objects.create(user=self.user, name="Old Wallet", type="other")
        url = reverse("wallet_delete", kwargs={"pk": extra_w.pk})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("wallet_list"))
        self.assertFalse(Wallet.objects.filter(pk=extra_w.pk).exists())

    def test_wallet_delete_prevent_last_wallet(self):
        self.client.force_login(self.user)
        # Delete wallet2 so only wallet1 remains
        self.wallet2.delete()
        self.assertEqual(Wallet.objects.filter(user=self.user).count(), 1)

        url = reverse("wallet_delete", kwargs={"pk": self.wallet1.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, reverse("wallet_list"))
        self.assertTrue(Wallet.objects.filter(pk=self.wallet1.pk).exists())

        # Also verify POST is blocked
        resp_post = self.client.post(url)
        self.assertEqual(resp_post.status_code, 302)
        self.assertRedirects(resp_post, reverse("wallet_list"))
        self.assertTrue(Wallet.objects.filter(pk=self.wallet1.pk).exists())

    def test_wallet_delete_buttons_in_templates(self):
        self.client.force_login(self.user)
        # Wallet list page has delete button
        resp_list = self.client.get(reverse("wallet_list"))
        self.assertEqual(resp_list.status_code, 200)
        self.assertContains(resp_list, reverse("wallet_delete", kwargs={"pk": self.wallet1.pk}))

        # Wallet edit page has delete button
        resp_edit = self.client.get(reverse("wallet_edit", kwargs={"pk": self.wallet1.pk}))
        self.assertEqual(resp_edit.status_code, 200)
        self.assertContains(resp_edit, reverse("wallet_delete", kwargs={"pk": self.wallet1.pk}))

    def test_wallet_card_clickable_to_edit(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("wallet_list"))
        self.assertEqual(resp.status_code, 200)
        # Card contains stretched w-card-link pointing to wallet_edit
        edit_url = reverse("wallet_edit", kwargs={"pk": self.wallet1.pk})
        self.assertContains(resp, f'class="w-card-link" href="{edit_url}"')
        # Edit icon button is removed from w-grid-actions
        self.assertNotContains(resp, f'class="icon-btn w-action-btn" href="{edit_url}"')


class SvgSpriteTests(TestCase):
    def test_master_svg_sprite_file_and_symbols(self):
        import os
        import re
        master_path = os.path.abspath("static/img/icons.svg")
        self.assertTrue(os.path.exists(master_path), "Master icons.svg must exist")
        
        with open(master_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        symbols = re.findall(r'<symbol id="icon-([^"]+)"', content)
        self.assertGreaterEqual(len(symbols), 3900, "Master sprite should contain all Material Symbols")
        self.assertIn("sports_soccer", symbols)
        self.assertIn("hiking", symbols)
        self.assertIn("restaurant", symbols)
        self.assertIn("account_balance_wallet", symbols)

    def test_inline_svg_symbols_file(self):
        import os
        inline_path = os.path.abspath("templates/tracker/_svg_symbols.html")
        self.assertTrue(os.path.exists(inline_path), "_svg_symbols.html must exist")

    def test_material_symbols_font_retired(self):
        import os
        font_path = os.path.abspath("static/fonts/material-symbols-rounded.woff2")
        self.assertFalse(os.path.exists(font_path), "5.36MB font file must remain removed")

    def test_wang_icons_template_tag(self):
        from tracker.templatetags import wang_icons
        # Core icon resolves to inline #icon-
        rendered_core = str(wang_icons.icon("restaurant"))
        self.assertIn('href="#icon-restaurant"', rendered_core)

        # Extended icon resolves to master sprite /static/img/icons.svg#icon-
        rendered_ext = str(wang_icons.icon("sports_soccer"))
        self.assertIn('href="/static/img/icons.svg#icon-sports_soccer"', rendered_ext)

        # icon_href tag
        self.assertEqual(wang_icons.icon_href("restaurant"), "#icon-restaurant")
        self.assertEqual(wang_icons.icon_href("sports_soccer"), "/static/img/icons.svg#icon-sports_soccer")


class DebtTests(TestCase):
    def setUp(self):
        from tracker.models import Debt, DebtPayment
        self.user = User.objects.create_user(username="debtuser", password="password123")
        self.other_user = User.objects.create_user(username="otheruser", password="password123")
        self.client = Client()
        self.client.login(username="debtuser", password="password123")

        self.wallet = Wallet.objects.create(
            user=self.user,
            name="Bank BCA",
            type="bank",
            initial_balance=Decimal("1000000"),
        )

    def test_debt_model_and_properties(self):
        from tracker.models import Debt, DebtPayment
        debt = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.LENT,
            person_name="Budi",
            amount=Decimal("500000"),
            wallet=self.wallet,
            due_date=timezone.localdate() + timedelta(days=5),
            note="Lunch and movie",
        )
        self.assertEqual(debt.total_paid, Decimal("0"))
        self.assertEqual(debt.remaining_amount, Decimal("500000"))
        self.assertEqual(debt.paid_percentage, 0.0)
        self.assertFalse(debt.is_settled)
        self.assertEqual(debt.status, Debt.Status.PENDING)
        self.assertIn("In 5 days", debt.status_badge["label"])

        # Record partial repayment
        p1 = DebtPayment.objects.create(
            debt=debt,
            amount=Decimal("200000"),
            wallet=self.wallet,
            note="Transfer 200k",
        )
        debt.refresh_from_db()
        self.assertEqual(debt.total_paid, Decimal("200000"))
        self.assertEqual(debt.remaining_amount, Decimal("300000"))
        self.assertEqual(debt.paid_percentage, 40.0)
        self.assertEqual(debt.status, Debt.Status.PARTIAL)
        self.assertFalse(debt.is_settled)

        # Record remaining repayment
        p2 = DebtPayment.objects.create(
            debt=debt,
            amount=Decimal("300000"),
            wallet=self.wallet,
        )
        debt.refresh_from_db()
        self.assertEqual(debt.total_paid, Decimal("500000"))
        self.assertEqual(debt.remaining_amount, Decimal("0"))
        self.assertEqual(debt.paid_percentage, 100.0)
        self.assertEqual(debt.status, Debt.Status.SETTLED)
        self.assertTrue(debt.is_settled)
        self.assertEqual(debt.status_badge["label"], "Settled")

        # Deleting payment resets status
        p2.delete()
        debt.refresh_from_db()
        self.assertEqual(debt.total_paid, Decimal("200000"))
        self.assertEqual(debt.status, Debt.Status.PARTIAL)

    def test_debt_list_view_and_aggregation(self):
        from tracker.models import Debt, DebtPayment
        # Lent debt (Piutang): 400,000 with 100,000 paid -> 300,000 remaining
        d1 = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.LENT,
            person_name="Alice",
            amount=Decimal("400000"),
        )
        DebtPayment.objects.create(debt=d1, amount=Decimal("100000"))

        # Borrowed debt (Utang): 200,000 with 0 paid -> 200,000 remaining
        d2 = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.BORROWED,
            person_name="Charlie",
            amount=Decimal("200000"),
        )

        # Settled debt: 150,000 with 150,000 paid -> 0 remaining
        d3 = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.LENT,
            person_name="Dave",
            amount=Decimal("150000"),
        )
        DebtPayment.objects.create(debt=d3, amount=Decimal("150000"))

        resp = self.client.get(reverse("debt_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["total_lent_remaining"], Decimal("300000"))
        self.assertEqual(resp.context["total_borrowed_remaining"], Decimal("200000"))
        self.assertEqual(resp.context["net_debt"], Decimal("100000"))
        self.assertEqual(resp.context["active_count"], 2)
        self.assertEqual(resp.context["settled_count"], 1)

        # Filter tabs
        resp_lent = self.client.get(reverse("debt_list") + "?tab=lent")
        self.assertEqual(len(resp_lent.context["debts"]), 1)
        self.assertEqual(resp_lent.context["debts"][0].person_name, "Alice")

        resp_borrowed = self.client.get(reverse("debt_list") + "?tab=borrowed")
        self.assertEqual(len(resp_borrowed.context["debts"]), 1)
        self.assertEqual(resp_borrowed.context["debts"][0].person_name, "Charlie")

        resp_settled = self.client.get(reverse("debt_list") + "?tab=settled")
        self.assertEqual(len(resp_settled.context["debts"]), 1)
        self.assertEqual(resp_settled.context["debts"][0].person_name, "Dave")

    def test_debt_crud_views(self):
        from tracker.models import Debt
        # 1. Create debt
        url_create = reverse("debt_create")
        data = {
            "kind": "borrowed",
            "person_name": "Eko",
            "amount": "350000",
            "due_date": "2026-10-15",
            "note": "Office party contribution",
            "wallet": str(self.wallet.pk),
        }
        res_c = self.client.post(url_create, data)
        self.assertRedirects(res_c, reverse("debt_list"))
        debt = Debt.objects.get(person_name="Eko", user=self.user)
        self.assertEqual(debt.amount, Decimal("350000"))
        self.assertEqual(debt.kind, Debt.Kind.BORROWED)

        # 2. Edit debt
        url_edit = reverse("debt_edit", args=[debt.pk])
        res_e = self.client.post(url_edit, {
            "kind": "borrowed",
            "person_name": "Eko Purnomo",
            "amount": "400000",
            "due_date": "2026-10-20",
            "note": "Updated note",
            "wallet": str(self.wallet.pk),
        })
        self.assertRedirects(res_e, reverse("debt_list"))
        debt.refresh_from_db()
        self.assertEqual(debt.person_name, "Eko Purnomo")
        self.assertEqual(debt.amount, Decimal("400000"))

        # 3. Partial payment
        url_pay = reverse("debt_payment_create", args=[debt.pk])
        res_p = self.client.post(url_pay, {
            "amount": "150000",
            "wallet": str(self.wallet.pk),
            "note": "Part 1",
        })
        self.assertRedirects(res_p, reverse("debt_list"))
        debt.refresh_from_db()
        self.assertEqual(debt.total_paid, Decimal("150000"))
        self.assertEqual(debt.status, Debt.Status.PARTIAL)

        # 4. Settle in full
        url_settle = reverse("debt_settle", args=[debt.pk])
        res_s = self.client.post(url_settle)
        self.assertRedirects(res_s, reverse("debt_list"))
        debt.refresh_from_db()
        self.assertTrue(debt.is_settled)
        self.assertEqual(debt.remaining_amount, Decimal("0"))

        # 5. Delete debt
        url_del = reverse("debt_delete", args=[debt.pk])
        res_d = self.client.post(url_del)
        self.assertRedirects(res_d, reverse("debt_list"))
        self.assertFalse(Debt.objects.filter(pk=debt.pk).exists())

    def test_debt_user_isolation(self):
        from tracker.models import Debt
        other_debt = Debt.objects.create(
            user=self.other_user,
            kind=Debt.Kind.BORROWED,
            person_name="Private",
            amount=Decimal("1000000"),
        )
        res = self.client.get(reverse("debt_edit", args=[other_debt.pk]))
        self.assertEqual(res.status_code, 404)
        res_s = self.client.post(reverse("debt_settle", args=[other_debt.pk]))
        self.assertEqual(res_s.status_code, 404)
        res_d = self.client.post(reverse("debt_delete", args=[other_debt.pk]))
        self.assertEqual(res_d.status_code, 404)

    def test_debt_list_view_and_sheet_structure(self):
        res = self.client.get(reverse("debt_list"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn('id="debt-pay-sheet"', content)
        self.assertIn('class="sheet debt-pay-sheet"', content)
        # Verify it is in sheet-root-container and outside <main>
        self.assertIn('id="sheet-root-container"', content)
        sheet_pos = content.find('id="debt-pay-sheet"')
        root_pos = content.find('id="sheet-root-container"')
    def test_debt_payment_syncs_wallet_balance_and_reversal(self):
        from tracker.models import Debt, DebtPayment, Transaction
        init_balance = self.wallet.current_balance

        # 1. Borrowed debt: Repayment should DEDUCT from wallet (Expense)
        borrowed = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.BORROWED,
            person_name="Lender Friend",
            amount=Decimal("200000"),
            wallet=self.wallet,
        )
        url_pay = reverse("debt_payment_create", args=[borrowed.pk])
        res1 = self.client.post(url_pay, {
            "amount": "50000",
            "wallet": str(self.wallet.pk),
            "note": "Paid cash",
        })
        self.assertRedirects(res1, reverse("debt_list"))
        
        # Verify wallet balance decreased
        self.assertEqual(self.wallet.current_balance, init_balance - Decimal("50000"))
        payment1 = borrowed.payments.first()
        self.assertIsNotNone(payment1.transaction)
        self.assertEqual(payment1.transaction.kind, Transaction.Kind.EXPENSE)
        self.assertEqual(payment1.transaction.category.name, "Utangs")
        self.assertEqual(payment1.transaction.amount, Decimal("50000"))
        self.assertIn("Debt repayment to Lender Friend", payment1.transaction.note)

        # 2. Lent debt: Repayment should DEPOSIT into wallet (Income)
        lent = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.LENT,
            person_name="Borrower Colleague",
            amount=Decimal("300000"),
            wallet=self.wallet,
        )
        url_pay_lent = reverse("debt_payment_create", args=[lent.pk])
        res2 = self.client.post(url_pay_lent, {
            "amount": "80000",
            "wallet": str(self.wallet.pk),
            "note": "Via bank transfer",
        })
        self.assertRedirects(res2, reverse("debt_list"))
        
        # Verify wallet balance increased by 80,000
        self.assertEqual(self.wallet.current_balance, init_balance - Decimal("50000") + Decimal("80000"))
        payment2 = lent.payments.first()
        self.assertIsNotNone(payment2.transaction)
        self.assertEqual(payment2.transaction.kind, Transaction.Kind.INCOME)
        self.assertEqual(payment2.transaction.category.name, "Utangs")
        self.assertEqual(payment2.transaction.amount, Decimal("80000"))

        # 3. Deleting a payment should clean up its linked transaction and restore wallet balance
        tx2_id = payment2.transaction.id
        payment2.delete()
        self.assertFalse(Transaction.objects.filter(id=tx2_id).exists())
        self.assertEqual(self.wallet.current_balance, init_balance - Decimal("50000"))

    def test_debt_creation_and_deletion_syncs_wallet_balance(self):
        from tracker.models import Debt, Transaction
        init_balance = self.wallet.current_balance

        # 1. Create LENT debt with wallet: should deduct wallet balance (Expense)
        res_create_lent = self.client.post(reverse("debt_create"), {
            "kind": "lent",
            "person_name": "Lent Friend",
            "amount": "120000",
            "wallet": str(self.wallet.pk),
            "note": "Lunch treat loan",
        })
        self.assertRedirects(res_create_lent, reverse("debt_list"))
        lent_debt = Debt.objects.get(person_name="Lent Friend")
        self.assertIsNotNone(lent_debt.transaction)
        self.assertEqual(lent_debt.transaction.kind, Transaction.Kind.EXPENSE)
        self.assertEqual(lent_debt.transaction.category.name, "Utangs")
        self.assertEqual(lent_debt.transaction.amount, Decimal("120000"))
        self.assertEqual(self.wallet.current_balance, init_balance - Decimal("120000"))

        # 2. Create BORROWED debt with wallet: should increase wallet balance (Income)
        res_create_borrowed = self.client.post(reverse("debt_create"), {
            "kind": "borrowed",
            "person_name": "Borrow Friend",
            "amount": "250000",
            "wallet": str(self.wallet.pk),
            "note": "Emergency cash",
        })
        self.assertRedirects(res_create_borrowed, reverse("debt_list"))
        borrowed_debt = Debt.objects.get(person_name="Borrow Friend")
        self.assertIsNotNone(borrowed_debt.transaction)
        self.assertEqual(borrowed_debt.transaction.kind, Transaction.Kind.INCOME)
        self.assertEqual(borrowed_debt.transaction.category.name, "Utangs")
        self.assertEqual(borrowed_debt.transaction.amount, Decimal("250000"))
        self.assertEqual(self.wallet.current_balance, init_balance - Decimal("120000") + Decimal("250000"))

        # 3. Create debt without wallet (pure ledger): does NOT affect wallet balance
        bal_before = self.wallet.current_balance
        res_create_pure = self.client.post(reverse("debt_create"), {
            "kind": "borrowed",
            "person_name": "Paper Debt",
            "amount": "50000",
            "wallet": "",
        })
        self.assertRedirects(res_create_pure, reverse("debt_list"))
        pure_debt = Debt.objects.get(person_name="Paper Debt")
        self.assertIsNone(pure_debt.transaction)
        self.assertEqual(self.wallet.current_balance, bal_before)

        # 4. Deleting debt removes linked transaction and reverts wallet balance
        tx_borrowed_id = borrowed_debt.transaction.id
        self.client.post(reverse("debt_delete", args=[borrowed_debt.pk]))
        self.assertFalse(Transaction.objects.filter(id=tx_borrowed_id).exists())
        self.assertEqual(self.wallet.current_balance, init_balance - Decimal("120000"))

    def test_dashboard_debts_carousel_and_dashboard_redirect(self):
        from tracker.models import Debt
        # Create active debt
        active = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.LENT,
            person_name="Budi Utomo",
            amount=Decimal("350000"),
        )
        # Create settled debt (should not appear in carousel)
        settled = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.BORROWED,
            person_name="Settled Pal",
            amount=Decimal("100000"),
            status=Debt.Status.SETTLED,
        )

        res = self.client.get(reverse("dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("active_debts", res.context)
        active_debts = res.context["active_debts"]
        self.assertIn(active, active_debts)
        self.assertNotIn(settled, active_debts)

        content = res.content.decode("utf-8")
        self.assertIn('id="tab-btn-subs"', content)
        self.assertIn('id="tab-btn-debts"', content)
        self.assertIn('id="strip-subs"', content)
        self.assertIn('id="strip-debts"', content)
        self.assertIn('Budi Utomo', content)
        self.assertIn('js-open-debt-pay', content)

        # Repayment initiated from dashboard redirects back to dashboard
        url_pay = reverse("debt_payment_create", args=[active.pk])
        res_pay = self.client.post(
            url_pay,
            {"amount": "50000", "wallet": str(self.wallet.pk)},
            HTTP_REFERER="http://testserver/"
        )
        self.assertRedirects(res_pay, reverse("dashboard"))
        active.refresh_from_db()
        self.assertEqual(active.remaining_amount, Decimal("300000"))


class MoreHubTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from tracker.models import Wallet, Category
        self.user = get_user_model().objects.create_user(username="moreuser", password="password123")
        self.client.login(username="moreuser", password="password123")
        self.wallet = Wallet.objects.create(user=self.user, name="Main", initial_balance=Decimal("500000"))
        self.cat = Category.objects.create(user=self.user, name="Coffee", kind="expense", icon="coffee", color="#8D6E63")

    def test_more_view_renders_cards_and_metrics(self):
        from tracker.models import Subscription, Debt
        Subscription.objects.create(
            user=self.user,
            name="Netflix",
            amount=Decimal("186000"),
            cycle="monthly",
            due_day=15,
            wallet=self.wallet,
            category=self.cat,
            active=True
        )
        Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.BORROWED,
            person_name="Doni",
            amount=Decimal("200000"),
        )

        res = self.client.get(reverse("more"))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, "tracker/more.html")
        self.assertEqual(res.context["categories_count"], 1)
        self.assertEqual(res.context["active_subs_count"], 1)
        self.assertEqual(res.context["active_debts_count"], 1)

        content = res.content.decode("utf-8")
        self.assertIn("Categories", content)
        self.assertIn("Recurring Payments", content)
        self.assertIn("Debts &amp; Loans", content)
        self.assertIn("Export Data to CSV", content)
        self.assertIn("Appearance", content)
        self.assertIn("Sound Effects", content)
        self.assertIn("Log Out", content)
        # Verify 5th tab in bottomnav is More
        self.assertIn('data-nav="more"', content)
        self.assertIn('>More</small>', content)

    def test_category_list_has_back_to_more(self):
        res = self.client.get(reverse("category_list"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn(reverse("more"), content)
        # Verify recurring payments banner is no longer inside category_list
        self.assertNotIn('class="card sub-banner-card"', content)

    def test_sheet_context_default_wallet_from_last_transaction(self):
        from tracker.views import _sheet_context
        from tracker.models import Wallet, Transaction
        # By default (no tx), default_wallet is first wallet
        ctx = _sheet_context(self.user)
        self.assertEqual(ctx["default_wallet"].id, self.wallet.id)

        wallet2 = Wallet.objects.create(user=self.user, name="Secondary", initial_balance=Decimal("100000"))
        # Create a transaction using wallet2
        Transaction.objects.create(
            user=self.user,
            kind=Transaction.Kind.EXPENSE,
            amount=Decimal("15000"),
            wallet=wallet2,
            category=self.cat,
            note="Coffee",
        )
        ctx = _sheet_context(self.user)
        self.assertEqual(ctx["default_wallet"].id, wallet2.id)

    def test_login_page_renders_cleanly(self):
        res = self.client.get(reverse("login"))
        self.assertEqual(res.status_code, 200)
        content = res.content.decode("utf-8")
        self.assertIn("Welcome back", content)
        self.assertNotIn("toast-error", content)

    def test_login_failure_invalid_credentials_shows_toast_and_422(self):
        res = self.client.post(reverse("login"), {"username": "nonexistent", "password": "wrongpassword"})
        self.assertEqual(res.status_code, 422)
        content = res.content.decode("utf-8")
        self.assertIn("toast-error", content)
        self.assertIn("Invalid username or password. Please try again.", content)
        self.assertIn("auth-error-box", content)

    def test_login_failure_empty_fields_shows_toast_and_422(self):
        res = self.client.post(reverse("login"), {})
        self.assertEqual(res.status_code, 422)
        content = res.content.decode("utf-8")
        self.assertIn("toast-error", content)
        self.assertIn("Username and password are required.", content)

    def test_login_failure_missing_single_field_shows_toast(self):
        res_no_pw = self.client.post(reverse("login"), {"username": "user123"})
        self.assertEqual(res_no_pw.status_code, 422)
        self.assertIn("Please enter your password.", res_no_pw.content.decode("utf-8"))

        res_no_user = self.client.post(reverse("login"), {"password": "pwd"})
        self.assertEqual(res_no_user.status_code, 422)
        self.assertIn("Please enter your username.", res_no_user.content.decode("utf-8"))

    def test_login_success_redirects_to_dashboard(self):
        from django.contrib.auth.models import User
        User.objects.filter(username="test_auth_ok").delete()
        User.objects.create_user(username="test_auth_ok", password="SecurePassword123!")
        res = self.client.post(reverse("login"), {"username": "test_auth_ok", "password": "SecurePassword123!"})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), reverse("dashboard"))


class PaymentHistorySyncTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from tracker.models import Wallet, Category
        self.user = get_user_model().objects.create_user(username="syncuser", password="password123")
        self.client.login(username="syncuser", password="password123")
        self.wallet1 = Wallet.objects.create(user=self.user, name="Wallet 1", initial_balance=Decimal("1000000"))
        self.wallet2 = Wallet.objects.create(user=self.user, name="Wallet 2", initial_balance=Decimal("500000"))
        self.cat = Category.objects.create(user=self.user, name="Bills", kind="expense", icon="receipt", color="#FFB5A7")

    def test_subscription_payment_transaction_edit_syncs_history(self):
        from tracker.models import Subscription, SubscriptionPayment, Transaction
        sub = Subscription.objects.create(
            user=self.user,
            name="Cloud Storage",
            amount=Decimal("150000"),
            wallet=self.wallet1,
            category=self.cat,
            cycle="monthly",
            due_day=10,
        )
        self.client.post(reverse("subscription_pay", args=[sub.pk]))
        sub.refresh_from_db()
        self.assertTrue(sub.is_paid_this_cycle)

        payment = sub.payments.first()
        self.assertIsNotNone(payment)
        tx = payment.transaction
        self.assertIsNotNone(tx)

        # Edit transaction from dashboard
        tx.amount = Decimal("180000")
        tx.wallet = self.wallet2
        tx.note = "Updated invoice amount"
        tx.save()

        # Check SubscriptionPayment is synced
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("180000"))
        self.assertEqual(payment.wallet, self.wallet2)
        self.assertEqual(payment.note, "Updated invoice amount")

    def test_subscription_payment_transaction_delete_removes_history_and_resets_status(self):
        from tracker.models import Subscription, SubscriptionPayment, Transaction
        sub = Subscription.objects.create(
            user=self.user,
            name="Spotify Family",
            amount=Decimal("86000"),
            wallet=self.wallet1,
            category=self.cat,
            cycle="monthly",
            due_day=15,
        )
        self.client.post(reverse("subscription_pay", args=[sub.pk]))
        sub.refresh_from_db()
        self.assertTrue(sub.is_paid_this_cycle)
        self.assertEqual(sub.payments.count(), 1)

        tx = sub.payments.first().transaction
        # Delete transaction from dashboard
        self.client.post(reverse("transaction_delete", args=[tx.pk]))

        sub.refresh_from_db()
        self.assertEqual(sub.payments.count(), 0)
        self.assertIsNone(sub.last_paid_date)
        self.assertFalse(sub.is_paid_this_cycle)

    def test_debt_payment_transaction_edit_syncs_history_and_recalculates_debt(self):
        from tracker.models import Debt, DebtPayment, Transaction
        debt = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.BORROWED,
            person_name="Sarah",
            amount=Decimal("500000"),
            wallet=self.wallet1,
        )
        # Pay 200,000 partial
        self.client.post(reverse("debt_payment_create", args=[debt.pk]), {
            "amount": "200000",
            "wallet": str(self.wallet1.pk),
            "note": "First installment",
        })
        debt.refresh_from_db()
        self.assertEqual(debt.status, Debt.Status.PARTIAL)
        self.assertEqual(debt.remaining_amount, Decimal("300000"))

        payment = debt.payments.first()
        tx = payment.transaction

        # Edit transaction to 500,000 (full amount)
        tx.amount = Decimal("500000")
        tx.note = "Full amount paid"
        tx.save()

        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("500000"))
        self.assertEqual(payment.note, "Full amount paid")

        debt.refresh_from_db()
        self.assertEqual(debt.remaining_amount, Decimal("0"))
        self.assertEqual(debt.status, Debt.Status.SETTLED)

    def test_debt_payment_transaction_delete_removes_history_and_restores_balance(self):
        from tracker.models import Debt, DebtPayment, Transaction
        debt = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.BORROWED,
            person_name="Budi",
            amount=Decimal("300000"),
            wallet=self.wallet1,
        )
        # Pay full 300,000
        self.client.post(reverse("debt_settle", args=[debt.pk]))
        debt.refresh_from_db()
        self.assertEqual(debt.status, Debt.Status.SETTLED)
        self.assertEqual(debt.payments.count(), 1)

        tx = debt.payments.first().transaction
        # Delete transaction from dashboard
        self.client.post(reverse("transaction_delete", args=[tx.pk]))

        debt.refresh_from_db()
        self.assertEqual(debt.payments.count(), 0)
        self.assertEqual(debt.remaining_amount, Decimal("300000"))
        self.assertEqual(debt.status, Debt.Status.PENDING)

    def test_debt_origin_transaction_edit_syncs_debt_amount_and_wallet(self):
        from tracker.models import Debt, Transaction
        res = self.client.post(reverse("debt_create"), {
            "kind": "lent",
            "person_name": "Rian",
            "amount": "100000",
            "wallet": str(self.wallet1.pk),
        })
        self.assertRedirects(res, reverse("debt_list"))
        debt = Debt.objects.get(person_name="Rian")
        self.assertIsNotNone(debt.transaction)

        # Edit origin transaction
        tx = debt.transaction
        tx.amount = Decimal("250000")
        tx.wallet = self.wallet2
        tx.save()

        debt.refresh_from_db()
        self.assertEqual(debt.amount, Decimal("250000"))
        self.assertEqual(debt.wallet, self.wallet2)

    def test_dashboard_dual_header_spendable_and_net_worth(self):
        from tracker.models import Wallet
        # wallet1 (1,000,000, cash/spendable), wallet2 (500,000, bank/spendable)
        # create savings wallet (5,000,000, savings)
        savings = Wallet.objects.create(
            user=self.user,
            name="Emergency Fund",
            type=Wallet.WalletType.SAVINGS,
            initial_balance=Decimal("5000000"),
            include_in_total=False,
        )
        res = self.client.get(reverse("dashboard"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["spendable_balance"], Decimal("1500000"))
        self.assertEqual(res.context["net_worth"], Decimal("6500000"))
        self.assertEqual(res.context["savings_balance"], Decimal("5000000"))

        content = res.content.decode("utf-8")
        self.assertIn('id="hero-btn-spendable"', content)
        self.assertIn('id="hero-btn-savings"', content)
        self.assertIn('id="hero-btn-networth"', content)
        self.assertIn('data-raw-spendable="Rp1.500.000"', content)
        self.assertIn('data-raw-savings="Rp5.000.000"', content)
        self.assertIn('data-raw-networth="Rp6.500.000"', content)

    def test_wallet_list_3way_mode_switcher(self):
        from tracker.models import Wallet
        # wallet1 (1,000,000, cash/spendable), wallet2 (500,000, bank/spendable)
        savings = Wallet.objects.create(
            user=self.user,
            name="Emergency Fund",
            type=Wallet.WalletType.SAVINGS,
            initial_balance=Decimal("5000000"),
            include_in_total=False,
        )
        res = self.client.get(reverse("wallet_list"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["spendable_balance"], Decimal("1500000"))
        self.assertEqual(res.context["net_worth"], Decimal("6500000"))
        self.assertEqual(res.context["savings_balance"], Decimal("5000000"))

        content = res.content.decode("utf-8")
        self.assertIn('id="hero-btn-spendable"', content)
        self.assertIn('id="hero-btn-savings"', content)
        self.assertIn('id="hero-btn-networth"', content)
        self.assertIn('data-raw-spendable="Rp1.500.000"', content)
        self.assertIn('data-raw-savings="Rp5.000.000"', content)
        self.assertIn('data-raw-networth="Rp6.500.000"', content)


class UserProfileTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username="profiler", password="password123")
        self.client.login(username="profiler", password="password123")

    def test_user_profile_auto_created_and_helpers(self):
        from tracker.models import UserProfile
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.get_display_name(), "profiler")
        self.assertEqual(profile.get_initials(), "P")

        profile.display_name = "Raihan"
        profile.save()
        self.assertEqual(profile.get_display_name(), "Raihan")
        self.assertEqual(profile.get_initials(), "R")

    def test_more_view_contains_profile_card(self):
        res = self.client.get(reverse("more"))
        self.assertEqual(res.status_code, 200)
        self.assertIn("profile", res.context)
        content = res.content.decode("utf-8")
        self.assertIn("more-profile-card", content)
        self.assertIn(reverse("profile_edit"), content)

    def test_profile_edit_get_and_post(self):
        res_get = self.client.get(reverse("profile_edit"))
        self.assertEqual(res_get.status_code, 200)
        self.assertTemplateUsed(res_get, "tracker/profile_form.html")

        res_post = self.client.post(reverse("profile_edit"), {
            "display_name": "Raihan Finance",
            "bio": "Saving for Japan 🌸",
            "currency_symbol": "IDR",
        })
        self.assertEqual(res_post.status_code, 302)

        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.display_name, "Raihan Finance")
        self.assertEqual(self.user.profile.bio, "Saving for Japan 🌸")
        self.assertEqual(self.user.profile.currency_symbol, "IDR")

    def test_profile_avatar_upload_and_removal(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        img_io = io.BytesIO()
        image = Image.new("RGB", (300, 300), color="blue")
        image.save(img_io, format="JPEG")
        img_io.seek(0)

        uploaded = SimpleUploadedFile("my_avatar.jpg", img_io.getvalue(), content_type="image/jpeg")

        res = self.client.post(reverse("profile_edit"), {
            "display_name": "Raihan",
            "avatar": uploaded,
        })
        self.assertEqual(res.status_code, 302)

        self.user.profile.refresh_from_db()
        self.assertTrue(bool(self.user.profile.avatar))
        self.assertTrue(self.user.profile.avatar.name.endswith(".webp"))

        # Remove avatar
        res_rm = self.client.post(reverse("profile_remove_avatar"))
        self.assertEqual(res_rm.status_code, 302)
        self.user.profile.refresh_from_db()
        self.assertFalse(bool(self.user.profile.avatar))


class ReceiptScannerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="scanneruser", password="password123")
        self.client = Client()
        self.client.login(username="scanneruser", password="password123")
        self.cat_groceries = Category.objects.create(
            user=self.user,
            name="Groceries",
            kind="expense",
            icon="shopping_cart",
        )
        self.cat_food = Category.objects.create(
            user=self.user,
            name="Food & Drinks",
            kind="expense",
            icon="restaurant",
        )
        self.wallet_cash = Wallet.objects.create(
            user=self.user,
            name="Dompet Tunai",
            type=Wallet.WalletType.CASH,
            icon="payments",
        )
        self.wallet_bca = Wallet.objects.create(
            user=self.user,
            name="BCA Debit",
            type=Wallet.WalletType.BANK,
            icon="account_balance",
        )
        self.wallet_gopay = Wallet.objects.create(
            user=self.user,
            name="GoPay",
            type=Wallet.WalletType.EWALLET,
            icon="account_balance_wallet",
        )

    def test_scan_receipt_no_api_key(self):
        from tracker.receipt_scanner import scan_receipt_with_gemini
        result = scan_receipt_with_gemini(b"fake-image", api_key="")
        self.assertFalse(result["success"])
        self.assertIn("not configured", result["error"])

    def test_scan_receipt_success(self):
        import io
        from unittest.mock import patch, MagicMock
        from tracker.receipt_scanner import scan_receipt_with_gemini

        mock_gemini_response = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": json.dumps({
                                    "total_amount": 48500,
                                    "merchant": "Indomaret",
                                    "items": ["Susu UHT", "Roti Tawar"],
                                    "note": "Indomaret - Susu UHT, Roti Tawar",
                                    "suggested_category": "Groceries",
                                    "payment_method": "Tunai",
                                    "suggested_wallet": "Dompet Tunai",
                                    "discount_amount": 5000,
                                    "date": "2026-09-17",
                                })
                            }
                        ]
                    }
                }
            ]
        }

        mock_http_res = MagicMock()
        mock_http_res.read.return_value = json.dumps(mock_gemini_response).encode("utf-8")
        mock_http_res.__enter__.return_value = mock_http_res

        with patch("urllib.request.urlopen", return_value=mock_http_res):
            result = scan_receipt_with_gemini(
                b"fake-image-bytes",
                mime_type="image/jpeg",
                category_names=["Groceries", "Food & Drinks"],
                wallet_options=[{"name": "Dompet Tunai", "type": "cash"}, {"name": "BCA Debit", "type": "bank"}],
                api_key="test-gemini-key",
            )
            self.assertTrue(result["success"])
            self.assertEqual(result["total_amount"], 48500)
            self.assertEqual(result["merchant"], "Indomaret")
            self.assertEqual(result["note"], "Indomaret - Susu UHT, Roti Tawar")
            self.assertEqual(result["suggested_category"], "Groceries")
            self.assertEqual(result["payment_method"], "Tunai")
            self.assertEqual(result["suggested_wallet"], "Dompet Tunai")
            self.assertEqual(result["discount_amount"], 5000)
            self.assertEqual(result["date"], "2026-09-17")

    def test_api_scan_receipt_endpoint_no_image(self):
        url = reverse("api_scan_receipt")
        res = self.client.post(url, {})
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data["success"])

    def test_api_scan_receipt_endpoint_unauthenticated(self):
        anonymous_client = Client()
        url = reverse("api_scan_receipt")
        res = anonymous_client.post(url, {})
        self.assertEqual(res.status_code, 302)

    def test_api_scan_receipt_endpoint_success(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile("receipt.jpg", b"fake-receipt-content", content_type="image/jpeg")

        with patch("tracker.views.scan_receipt_with_gemini") as mock_scan:
            mock_scan.return_value = {
                "success": True,
                "total_amount": 75000,
                "merchant": "KFC",
                "note": "KFC - 2x Super Besar 1",
                "suggested_category": "Food & Drinks",
                "suggested_wallet": "BCA Debit",
                "payment_method": "Debit BCA",
                "discount_amount": 12500,
                "date": "2026-09-17T13:45",
                "error": None,
            }
            url = reverse("api_scan_receipt")
            res = self.client.post(url, {"image": uploaded})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["total_amount"], 75000)
            self.assertEqual(data["merchant"], "KFC")
            self.assertEqual(data["note"], "KFC - 2x Super Besar 1")
            self.assertEqual(data["category_id"], self.cat_food.id)
            self.assertEqual(data["category_name"], "Food & Drinks")
            self.assertEqual(data["wallet_id"], self.wallet_bca.id)
            self.assertEqual(data["wallet_name"], "BCA Debit")
            self.assertEqual(data["payment_method"], "Debit BCA")
            self.assertEqual(data["discount_amount"], 12500)
            self.assertEqual(data["date"], "2026-09-17T13:45")

    def test_api_scan_receipt_wallet_matching_heuristics(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile("receipt.jpg", b"fake-receipt-content", content_type="image/jpeg")
        url = reverse("api_scan_receipt")

        # Case 1: Tunai matches Cash wallet
        with patch("tracker.views.scan_receipt_with_gemini") as mock_scan:
            mock_scan.return_value = {
                "success": True,
                "total_amount": 25000,
                "merchant": "Warung Makan",
                "note": "Warung Makan - Nasi Goreng",
                "suggested_category": "Food & Drinks",
                "suggested_wallet": None,
                "payment_method": "Tunai",
                "discount_amount": 0,
                "date": "2026-09-17",
                "error": None,
            }
            res = self.client.post(url, {"image": uploaded})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["wallet_id"], self.wallet_cash.id)

        # Case 2: QRIS matches GoPay (E-Wallet)
        with patch("tracker.views.scan_receipt_with_gemini") as mock_scan:
            mock_scan.return_value = {
                "success": True,
                "total_amount": 35000,
                "merchant": "Kopi Kenangan",
                "note": "Kopi Kenangan - Kopi Kenangan Mantan",
                "suggested_category": "Food & Drinks",
                "suggested_wallet": None,
                "payment_method": "QRIS GoPay",
                "discount_amount": 7000,
                "date": "2026-09-17",
                "error": None,
            }
            res = self.client.post(url, {"image": uploaded})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["wallet_id"], self.wallet_gopay.id)
            self.assertEqual(data["discount_amount"], 7000)

    def test_api_scan_receipt_non_receipt_image(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile

        uploaded = SimpleUploadedFile("selfie.jpg", b"fake-selfie-content", content_type="image/jpeg")
        url = reverse("api_scan_receipt")

        with patch("tracker.views.scan_receipt_with_gemini") as mock_scan:
            mock_scan.return_value = {
                "success": True,
                "total_amount": None,
                "merchant": "",
                "note": "",
                "suggested_category": None,
                "suggested_wallet": None,
                "payment_method": None,
                "discount_amount": 0,
                "date": None,
                "error": None,
            }
            res = self.client.post(url, {"image": uploaded})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["success"])
            self.assertIsNone(data["total_amount"])
            self.assertEqual(data["merchant"], "")
            self.assertEqual(data["note"], "")
            self.assertEqual(data["category_id"], None)
            self.assertEqual(data["wallet_id"], None)
            self.assertEqual(data["discount_amount"], 0)


class DebtPaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="debtuser", password="password123")
        self.client = Client()
        self.client.login(username="debtuser", password="password123")

        self.wallet = Wallet.objects.create(
            user=self.user,
            name="Bank BCA",
            type="bank",
            initial_balance=Decimal("1000000"),
        )

    def test_debt_payment_create_and_delete(self):
        from tracker.models import Debt, DebtPayment
        # Create a borrowed debt: I owe John Rp500,000
        debt = Debt.objects.create(
            user=self.user,
            kind=Debt.Kind.BORROWED,
            person_name="John",
            amount=Decimal("500000"),
            wallet=None,
            due_date=date(2026, 10, 1),
        )
        self.assertEqual(debt.status, Debt.Status.PENDING)
        self.assertEqual(debt.remaining_amount, Decimal("500000"))

        # 1. Pay partial: Rp200,000 from Bank BCA
        pay_url = reverse("debt_payment_create", kwargs={"pk": debt.pk})
        res = self.client.post(pay_url, {
            "amount": "200000",
            "wallet": str(self.wallet.pk),
            "note": "First installment",
        })
        self.assertEqual(res.status_code, 302)

        debt.refresh_from_db()
        self.assertEqual(debt.status, Debt.Status.PARTIAL)
        self.assertEqual(debt.remaining_amount, Decimal("300000"))
        self.assertEqual(debt.payments.count(), 1)
        self.assertEqual(self.wallet.current_balance, Decimal("800000"))  # 1,000,000 - 200,000

        payment = debt.payments.first()
        self.assertIsNotNone(payment.transaction)
        self.assertEqual(payment.amount, Decimal("200000"))

        # 2. Delete the payment
        del_url = reverse("debt_payment_delete", kwargs={"pk": debt.pk, "payment_pk": payment.pk})
        del_res = self.client.post(del_url)
        self.assertEqual(del_res.status_code, 302)

        # Check debt status reverted to PENDING and remaining amount restored
        debt.refresh_from_db()
        self.assertEqual(debt.status, Debt.Status.PENDING)
        self.assertEqual(debt.remaining_amount, Decimal("500000"))
        self.assertEqual(debt.payments.count(), 0)
        # Check wallet balance restored
        self.assertEqual(self.wallet.current_balance, Decimal("1000000"))
        # Check transaction deleted
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 0)
