from django.db import migrations


def reset_include_in_total(apps, schema_editor):
    Wallet = apps.get_model("tracker", "Wallet")
    Wallet.objects.filter(include_in_total=False).update(include_in_total=True)


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0018_subscription_total_amount_and_more"),
    ]

    operations = [
        migrations.RunPython(reset_include_in_total, migrations.RunPython.noop),
    ]
