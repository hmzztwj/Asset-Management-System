"""领用 / 归还 / 删除 与资产台账的联动测试（业务口径命脉）。

口径（用户确认过的，勿擅改）：
- 借出：资产状态→「借出」，责任人→领用人，实际使用人→表单值（空则同领用人），部门→领用部门
- 归还：资产状态→「库存」，责任人/实际使用人→「资产管理员」，部门→「综合管理部」
- 逾期是派生状态（借出 + due_date 已过），绝不入库、不触发资产回收
- 删除领用记录等价于归还（无其它在借时复位资产）
"""
import datetime

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset, Requisition
from assets.tests.base import make_asset, make_department

TODAY = timezone.localdate


class BorrowLinkageTests(TestCase):
    """借出联动。"""

    def setUp(self):
        self.dept = make_department('研发一部')
        self.default_dept = make_department('综合管理部')
        self.asset = make_asset(department=self.default_dept)

    def test_borrow_syncs_asset(self):
        req = Requisition.objects.create(
            asset=self.asset, user='张三', actual_user='李四',
            department=self.dept, purpose='开发用', due_date=TODAY() + datetime.timedelta(days=7),
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, '借出')
        self.assertEqual(self.asset.responsible, '张三')
        self.assertEqual(self.asset.user, '李四')          # 实际使用人=表单值
        self.assertEqual(self.asset.department_id, self.dept.pk)

    def test_borrow_blank_actual_user_defaults_to_borrower(self):
        Requisition.objects.create(
            asset=self.asset, user='张三', actual_user='',
            department=self.dept, purpose='值班', due_date=TODAY(),
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.user, '张三')          # 留空即同领用人

    def test_borrow_without_department_keeps_original(self):
        Requisition.objects.create(
            asset=self.asset, user='张三', purpose='临时',
            due_date=TODAY() + datetime.timedelta(days=1),
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.department_id, self.default_dept.pk)  # 保持原部门


class ReturnLinkageTests(TestCase):
    """归还联动。"""

    def setUp(self):
        self.dept = make_department('研发一部')
        self.default_dept = make_department('综合管理部')
        self.asset = make_asset(department=self.default_dept)
        self.req = Requisition.objects.create(
            asset=self.asset, user='张三', department=self.dept,
            purpose='开发用', due_date=TODAY() - datetime.timedelta(days=1),  # 已逾期
        )

    def test_return_resets_asset(self):
        self.req.status = '已归还'
        self.req.return_date = TODAY()
        self.req.save()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, '库存')
        self.assertEqual(self.asset.responsible, '资产管理员')
        self.assertEqual(self.asset.user, '资产管理员')
        self.assertEqual(self.asset.department_id, self.default_dept.pk)

    def test_overdue_return_still_resets(self):
        """逾期中的资产归还后同样复位（逾期不锁死资产）。"""
        self.assertEqual(self.req.display_status, '逾期')
        self.req.status = '已归还'
        self.req.save()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, '库存')

    def test_return_keeps_asset_out_when_other_borrow_exists(self):
        """同一资产有两条在借记录时，归还其中一条不复位资产。"""
        Requisition.objects.create(
            asset=self.asset, user='王五', department=self.dept,
            purpose='另一条在借', due_date=TODAY(),
        )
        self.req.status = '已归还'
        self.req.save()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, '借出')
        self.assertEqual(self.asset.responsible, '王五')    # 后一条在借覆盖责任人，资产仍为借出


class DeleteLinkageTests(TestCase):
    """删除领用记录的联动（delete 不走 save，单独覆盖）。"""

    def setUp(self):
        self.dept = make_department('研发一部')
        self.default_dept = make_department('综合管理部')
        self.asset = make_asset(department=self.default_dept)
        self.req = Requisition.objects.create(
            asset=self.asset, user='张三', department=self.dept,
            purpose='开发用', due_date=TODAY(),
        )

    def test_delete_resets_asset(self):
        self.req.delete()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, '库存')
        self.assertEqual(self.asset.responsible, '资产管理员')
        self.assertEqual(self.asset.department_id, self.default_dept.pk)

    def test_delete_keeps_asset_when_other_borrow_exists(self):
        Requisition.objects.create(
            asset=self.asset, user='王五', department=self.dept,
            purpose='另一条在借', due_date=TODAY(),
        )
        self.req.delete()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, '借出')


class OverdueDerivedStatusTests(TestCase):
    """逾期为派生状态，绝不入库。"""

    def test_overdue_is_derived_not_stored(self):
        dept = make_department()
        asset = make_asset(department=dept)
        req = Requisition.objects.create(
            asset=asset, user='张三', department=dept,
            due_date=TODAY() - datetime.timedelta(days=3),
        )
        req.refresh_from_db()
        self.assertEqual(req.status, '借出')               # 存储态只有借出/已归还
        self.assertEqual(req.display_status, '逾期')       # 展示态动态推导
        self.assertTrue(req.is_overdue)
        asset.refresh_from_db()
        self.assertEqual(asset.status, '借出')               # 逾期不回收资产

    def test_due_today_is_not_overdue(self):
        dept = make_department()
        asset = make_asset(department=dept)
        req = Requisition.objects.create(
            asset=asset, user='张三', department=dept, due_date=TODAY(),
        )
        self.assertFalse(req.is_overdue)
        self.assertEqual(req.display_status, '借出')
