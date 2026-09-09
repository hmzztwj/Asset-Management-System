# 数据清洗：将历史遗留的存储态「逾期」统一迁移为「借出」。
# 逾期此后由 Requisition.display_status 依据 due_date 动态推导，
# 不再作为可存储状态，避免旧脏数据与新口径冲突、以及误回收资产。
from django.db import migrations


def migrate_overdue_to_borrowed(apps, schema_editor):
    Requisition = apps.get_model("assets", "Requisition")
    # 逾期=借出但过期；仅把存储值改回借出即可，逾期与否由 due_date 动态判定
    updated = Requisition.objects.filter(status="逾期").update(status="借出")
    if updated:
        print(f"[data-migration] 将 {updated} 条领用记录由「逾期」存储态迁移为「借出」")


def reverse_migration(apps, schema_editor):
    # 反向无意义（逾期已改为派生），留空
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0008_alter_requisition_status"),
    ]

    operations = [
        migrations.RunPython(migrate_overdue_to_borrowed, reverse_migration),
    ]
