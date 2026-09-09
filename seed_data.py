"""一次性填充示例数据，便于演示仪表盘与各模块。用法: python seed_data.py"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'assets_system.settings')
django.setup()

from assets.models import Department, Asset, Requisition, AssetChange, Role, UserProfile


def ensure_roles():
    """预置系统内置角色。"""
    roles = {
        'super_admin': dict(name='超级管理员', description='拥有系统全部权限',
                           can_access_admin=True, view_assets=True, manage_assets=True,
                           view_org=True, manage_org=True, view_requisition=True,
                           manage_requisition=True, view_change=True, manage_change=True,
                           manage_users=True, is_system=True),
        'admin': dict(name='管理员', description='管理各模块数据',
                      can_access_admin=True, view_assets=True, manage_assets=True,
                      view_org=True, manage_org=True, view_requisition=True,
                      manage_requisition=True, view_change=True, manage_change=True,
                      manage_users=True, is_system=True),
        'user': dict(name='普通用户', description='只读浏览各模块',
                     can_access_admin=False, view_assets=True, manage_assets=False,
                     view_org=True, manage_org=False, view_requisition=True,
                     manage_requisition=False, view_change=True, manage_change=False,
                     manage_users=False, is_system=True),
    }
    for code, data in roles.items():
        Role.objects.update_or_create(code=code, defaults=data)


ensure_roles()

# 组织架构树（上下级）
def ensure_dept(name, parent=None, manager='', description=''):
    dept, _ = Department.objects.get_or_create(
        name=name,
        defaults={'parent': parent, 'manager': manager, 'description': description},
    )
    # 若部门已存在，补上父级与负责人
    if dept.parent_id != (parent.id if parent else None):
        dept.parent = parent
        dept.save()
    if manager and not dept.manager:
        dept.manager = manager
        dept.save(update_fields=['manager'])
    return dept


root = ensure_dept('集团总部', manager='总经理', description='集团总部')
rd = ensure_dept('研发中心', parent=root, manager='研发总监', description='研发中心')
mk = ensure_dept('市场中心', parent=root, manager='市场总监', description='市场中心')
sl = ensure_dept('销售中心', parent=root, manager='销售总监', description='销售中心')
zk = ensure_dept('职能中心', parent=root, manager='职能总监', description='职能中心')

departments = {}
departments['研发一部'] = ensure_dept('研发一部', parent=rd, manager='张伟', description='研发一部')
departments['研发二部'] = ensure_dept('研发二部', parent=rd, manager='李娜', description='研发二部')
departments['市场部'] = ensure_dept('市场部', parent=mk, manager='王强', description='市场部')
departments['销售部'] = ensure_dept('销售部', parent=sl, manager='赵敏', description='销售部')
departments['财务部'] = ensure_dept('财务部', parent=zk, manager='陈静', description='财务部')
departments['人力资源部'] = ensure_dept('人力资源部', parent=zk, manager='刘洋', description='人力资源部')
departments['行政部'] = ensure_dept('行政部', parent=zk, manager='孙磊', description='行政部')

# 资产台账
assets_data = []
# (名称, 类别, 部门, 状态, 价格, 位置)
plan = [
    # 研发一部
    ('ThinkPad 笔记本', '电脑', '研发一部', '在用', 8999, 'A-101'),
    ('MacBook Pro', '电脑', '研发一部', '在用', 16999, 'A-102'),
    ('DELL 显示器', '电脑', '研发一部', '在用', 1899, 'A-101'),
    ('研发服务器', '网络设备', '研发一部', '在用', 45000, '机房'),
    ('交换机 H3C', '网络设备', '研发一部', '在用', 3200, '机房'),
    ('版本库软件', '软件', '研发一部', '在用', 15000, '—'),
    ('工位办公桌', '办公家具', '研发一部', '在用', 1200, 'A-101'),
    ('打印机 HP', '办公电器', '研发一部', '在用', 2800, 'A-101'),
    # 研发二部
    ('MacBook Air', '电脑', '研发二部', '在用', 10999, 'B-201'),
    ('联想小新', '电脑', '研发二部', '在用', 5499, 'B-202'),
    ('测试服务器', '网络设备', '研发二部', '在用', 38000, '机房'),
    ('GitLab 授权', '软件', '研发二部', '在用', 12000, '—'),
    ('人体工学椅', '办公家具', '研发二部', '在用', 1500, 'B-201'),
    ('路由器', '网络设备', '研发二部', '在用', 899, 'B-201'),
    # 市场部
    ('TCL 一体机', '电脑', '市场部', '在用', 4299, 'C-301'),
    ('佳能单反相机', '办公电器', '市场部', '在用', 7899, 'C-301'),
    ('文案设计软件', '软件', '市场部', '在用', 6800, '—'),
    ('会议桌', '办公家具', '市场部', '在用', 4500, 'C-301'),
    ('投影仪', '办公电器', '市场部', '维修', 5600, 'C-302'),
    # 销售部
    ('戴尔笔记本', '电脑', '销售部', '在用', 6299, 'D-401'),
    ('华为笔记本', '电脑', '销售部', '库存', 7499, 'D-401'),
    ('SaaS 系统授权', '软件', '销售部', '在用', 30000, '—'),
    ('工位屏风', '办公家具', '销售部', '在用', 1800, 'D-401'),
    # 财务部
    ('惠普笔记本', '电脑', '财务部', '在用', 5599, 'E-501'),
    ('财务软件', '软件', '财务部', '在用', 42000, '—'),
    ('碎纸机', '办公电器', '财务部', '在用', 1200, 'E-501'),
    ('保险柜', '办公家具', '财务部', '在用', 3800, 'E-501'),
    # 人力资源部
    ('联想笔记本', '电脑', '人力资源部', '在用', 4999, 'F-601'),
    ('考勤系统', '软件', '人力资源部', '在用', 6600, '—'),
    ('档案柜', '办公家具', '人力资源部', '在用', 1600, 'F-601'),
    # 行政部
    ('前置备用机', '电脑', '行政部', '库存', 4299, 'G-701'),
    ('复印机', '办公电器', '行政部', '在用', 9800, 'G-701'),
    ('饮水机', '办公电器', '行政部', '在用', 900, 'G-701'),
    ('会议室桌椅', '办公家具', '行政部', '在用', 5600, 'G-702'),
    # 未分配库存
    ('备用显示器', '电脑', None, '库存', 1299, '仓库'),
    ('备用键盘', '电脑', None, '库存', 299, '仓库'),
    ('旧服务器', '网络设备', None, '报废', 8000, '仓库'),
]

for name, category, dept, status, price, loc in plan:
    from datetime import date
    spec_map = {
        '电脑': '14英寸 / 轻薄本',
        '办公家具': '标准规格',
        '网络设备': '千兆',
        '软件': '企业授权版',
        '办公电器': '标准型',
        '其他': '—',
    }
    conf_map = {
        '电脑': 'i5/16G/512G SSD/集显',
        '办公家具': '—',
        '网络设备': '24口千兆/企业级',
        '软件': '完整功能模块',
        '办公电器': '—',
        '其他': '—',
    }
    asset, created = Asset.objects.get_or_create(
        name=name,
        defaults={
            'asset_id': f'ZC-{Asset.objects.count() + 1:04d}',
            'category': category,
            'specification': spec_map.get(category, '—'),
            'configuration': conf_map.get(category, '—'),
            'user': departments.get(dept).manager if dept else '',
            'department': departments.get(dept) if dept else None,
            'status': status,
            'price': price,
            'location': loc,
            'purchase_date': date(2022, 1, 1),
        },
    )
    # 已存在的资产也补上规格/配置/实际使用人
    if (not asset.specification or not asset.configuration) and category in spec_map:
        asset.specification = spec_map[category]
        asset.configuration = conf_map[category]
        asset.save(update_fields=['specification', 'configuration'])
    if not asset.user and dept:
        asset.user = departments.get(dept).manager or ''
        asset.save(update_fields=['user'])
    assets_data.append(asset)

# 领用记录（仅首次生成，避免重复）
if assets_data and Requisition.objects.count() == 0:
    from datetime import date as _date
    Requisition.objects.create(
        asset=assets_data[0], user='张工', department=departments['研发一部'],
        purpose='日常开发', status='借出', due_date=_date(2024, 6, 6),
    )
    Requisition.objects.create(
        asset=assets_data[16], user='李美', department=departments['市场部'],
        purpose='市场活动', status='已归还',
        return_date=_date(2024, 6, 1), due_date=_date(2024, 5, 30),
    )
    Requisition.objects.create(
        asset=assets_data[18], user='王文', department=departments['市场部'],
        purpose='客户演示', status='借出', due_date=_date(2024, 5, 20),
        # 逾期为派生状态：借出 + 已过预计归还日期 => display_status 自动显示「逾期」
    )

# 变更记录（仅首次生成，避免重复）
# 说明：模块仅支持「部门转移」「状态变更」两类，示例数据使用合法类型。
if assets_data and AssetChange.objects.count() == 0:
    AssetChange.objects.create(
        asset=assets_data[18], change_type='状态变更', old_value='在用',
        new_value='维修', changed_by='赵敏', note='投影仪故障送修',
    )
    AssetChange.objects.create(
        asset=assets_data[10], change_type='部门转移', old_value='研发一部',
        new_value='研发二部', changed_by='刘洋', note='项目组调整',
    )

print('示例数据已生成：')
print(f'  部门: {Department.objects.count()}')
print(f'  资产: {Asset.objects.count()}')
print(f'  领用: {Requisition.objects.count()}')
print(f'  变更: {AssetChange.objects.count()}')
