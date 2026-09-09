"""从「实际数据/迈德固定资产在线表.xlsx」导入/同步真实资产数据（幂等）。

用法:
    python import_real_data.py           # 按财务编码 upsert 资产，不影响领用/变更记录
    python import_real_data.py --reset   # 先清空 资产/领用/变更/部门 后重建（慎用）

说明:
    - 资产台账按财务编码 update_or_create，重复执行安全（只新增/更新，不删除）。
    - 默认【不清空】领用(Requisition)与变更(AssetChange)，避免误删系统内已登记的业务记录。
    - 仅在显式传入 --reset 时，才会重建资产/领用/变更/部门。
"""
import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "assets_system.settings")
django.setup()

from openpyxl import load_workbook
from assets.models import Department, Asset, Requisition, AssetChange

path = os.path.join("实际数据", "迈德固定资产在线表.xlsx")
wb = load_workbook(path, data_only=True, read_only=True)
ws = wb.active
rows = list(ws.iter_rows(values_only=True))
header_idx = 2  # 第3行为表头
header = rows[header_idx]
data = rows[header_idx + 1:]

def col(row, i):
    if i >= len(row):
        return ''
    v = row[i]
    return '' if v is None else str(v).strip()

STATUS_MAP = {
    '在用': '在用', '报废': '报废',
    '借用': '库存', '借': '库存', '员工离职': '库存',
    '报修': '维修', '维修': '维修',
}
CAT_MAP = {'笔记本电脑': '电脑', '台式电脑': '电脑', '服务器': '网络设备', '网络设备': '网络设备',
           '显示器': '电脑', '办公家具': '办公家具', '打印机': '办公电器', '办公电器': '办公电器'}

# 0. 默认为「增量同步」：不清空领用/变更。仅 --reset 时重建整库
RESET = "--reset" in sys.argv
if RESET:
    # 真实 Excel 不含领用/变更；仅在显式重建时清空以保证与台账一致
    Requisition.objects.all().delete()
    AssetChange.objects.all().delete()
    # 重建组织架构前，先解除旧资产对部门的引用，避免重复部门
    Asset.objects.update(department=None)
    Department.objects.all().delete()
    print("[reset] 已清空 领用/变更/部门，开始重建资产台账与组织架构 ...")

# 1. 建立组织架构：责任公司 -> 责任部门（幂等）
company, _ = Department.objects.get_or_create(
    name=col(data[0], 3) or '公司',
    defaults={'manager': '', 'description': '责任公司'},
)
dept_map = {}
for r in data:
    dname = col(r, 4)
    if not dname:
        continue
    if dname not in dept_map:
        dept, _ = Department.objects.get_or_create(name=dname, defaults={'parent': company})
        dept_map[dname] = dept
print(f"公司：{company.name} | 部门：{len(dept_map)} 个")

# 2. 导入/更新资产（按财务编码 upsert，保证准确）
imported = 0
for r in data:
    asset_id = col(r, 20)  # 财务编码（唯一）
    if not asset_id:
        continue
    cat = col(r, 1)
    name = cat or col(r, 2) or '资产'
    user = col(r, 7)
    if user == '无':
        user = ''
    responsible = col(r, 5)
    serial = col(r, 11)
    status = STATUS_MAP.get(col(r, 0), '库存')
    category = CAT_MAP.get(cat, '其他')
    dept = dept_map.get(col(r, 4))
    specs = [col(r, 14), col(r, 15), col(r, 16), col(r, 17), col(r, 18), col(r, 19)]
    config = ' / '.join([s for s in specs if s and s != '无'])
    spec = col(r, 18) if col(r, 18) and col(r, 18) != '无' else (col(r, 19) if col(r, 19) else '')
    price = 0
    try:
        price = float(col(r, 21)) if col(r, 21) else 0
    except Exception:
        price = 0
    Asset.objects.update_or_create(
        asset_id=asset_id,
        defaults=dict(
            name=name, category=category, specification=spec, configuration=config,
            responsible=responsible, serial=serial, department=dept,
            user=user, status=status, price=price, location=col(r, 8),
        ),
    )
    imported += 1

print(f"导入完成：资产 {imported} 条")
print(f"部门 {Department.objects.count()} | 资产 {Asset.objects.count()} | 领用 {Requisition.objects.count()} | 变更 {AssetChange.objects.count()}")
