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
        self.assertContains(response, 'Total Balance')
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
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="balance-card"')
        self.assertContains(response, 'Total balance')
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
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-error-box")
        self.assertContains(response, "Invalid username or password")

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
        self.assertIn("Paid ✓", sub.status_badge["short_label"])
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
        self.assertIn("Paid ✓", sub_monthly.status_badge["short_label"])

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

        # Template must display Sunday · Sep 6
        self.assertContains(resp, "Sunday · Sep 6")

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












