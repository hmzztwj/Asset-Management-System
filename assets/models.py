from django.db import models


class Role(models.Model):
    """角色：定义各模块的读/写权限。"""
    name = models.CharField('角色名称', max_length=50, unique=True)
    code = models.CharField('编码', max_length=50, unique=True)
    description = models.CharField('说明', max_length=200, blank=True)
    is_system = models.BooleanField('系统内置', default=False)
    can_access_admin = models.BooleanField('访问后台', default=False)
    view_assets = models.BooleanField('查看资产库', default=True)
    manage_assets = models.BooleanField('管理资产库', default=False)
    view_org = models.BooleanField('查看组织架构', default=True)
    manage_org = models.BooleanField('管理组织架构', default=False)
    view_requisition = models.BooleanField('查看资产领用', default=True)
    manage_requisition = models.BooleanField('管理资产领用', default=False)
    view_change = models.BooleanField('查看资产变更', default=True)
    manage_change = models.BooleanField('管理资产变更', default=False)
    manage_users = models.BooleanField('管理用户/角色', default=False)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '角色'
        verbose_name_plural = '角色'
        ordering = ['id']

    def __str__(self):
        return self.name

    def perm_codes(self):
        """该角色允许的权限码（字段名）。"""
        fields = [
            'can_access_admin', 'view_assets', 'manage_assets', 'view_org', 'manage_org',
            'view_requisition', 'manage_requisition', 'view_change', 'manage_change',
            'manage_users',
        ]
        return [f for f in fields if getattr(self, f)]


class UserProfile(models.Model):
    """扩展 Django User：关联角色。"""
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='profile', verbose_name='用户'
    )
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, null=True, blank=True,
        related_name='profiles', verbose_name='角色',
    )

    class Meta:
        verbose_name = '用户档案'
        verbose_name_plural = '用户档案'

    def __str__(self):
        return self.user.username


class Department(models.Model):
    """组织架构 —— 部门/中心，支持上下级树状结构。"""
    name = models.CharField('部门名称', max_length=100, unique=True)
    manager = models.CharField('负责人', max_length=50, blank=True)
    description = models.CharField('部门描述', max_length=200, blank=True)
    parent = models.ForeignKey(
        'self',
        verbose_name='上级部门',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '部门'
        verbose_name_plural = '部门'
        ordering = ['id']

    def __str__(self):
        return self.name


class Asset(models.Model):
    """资产库 —— 资产台账。"""
    CATEGORY_CHOICES = [
        ('笔记本电脑', '笔记本电脑'),
        ('台式机电脑', '台式机电脑'),
        ('电脑', '电脑设备'),
        ('办公家具', '办公家具'),
        ('网络设备', '网络设备'),
        ('软件', '软件/系统'),
        ('办公电器', '办公电器'),
        ('其他', '其他'),
    ]
    STATUS_CHOICES = [
        ('在用', '在用'),
        ('库存', '库存'),
        ('借出', '借出'),
        ('维修', '维修'),
        ('报废', '报废'),
    ]
    # 外部数据（Excel 台账）里常见的类别写法 → 本系统标准分类。
    # 仅当原值不在 CATEGORY_CHOICES 时才查此表，避免误改合法值。
    CATEGORY_ALIAS = {
        '笔记本': '笔记本电脑',
        '笔记本电脑': '笔记本电脑',
        '台式机': '台式机电脑',
        '台式电脑': '台式机电脑',
        '台式机电脑': '台式机电脑',
        '交换机': '网络设备',
        '路由器': '网络设备',
        '服务器': '网络设备',
        '网络设备': '网络设备',
        '显示器': '电脑',
        '电脑': '电脑',
        '办公家具': '办公家具',
        '打印机': '办公电器',
        '办公电器': '办公电器',
    }
    # 外部数据里的使用状态写法 → 本系统标准状态
    STATUS_ALIAS = {
        '闲置': '库存',
        '待报废': '报废',
        '待维修': '维修',
        '报修': '维修',
        '借用': '库存',
        '员工离职': '库存',
    }

    asset_id = models.CharField('资产编号', max_length=30, unique=True)
    name = models.CharField('资产名称', max_length=120)
    category = models.CharField('资产类别', max_length=30, choices=CATEGORY_CHOICES, default='其他')
    specification = models.CharField('规格', max_length=200, blank=True)
    configuration = models.CharField('配置', max_length=500, blank=True)
    responsible = models.CharField('责任人', max_length=50, blank=True)
    serial = models.CharField('序列号', max_length=120, blank=True)
    department = models.ForeignKey(
        Department,
        verbose_name='所属部门',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assets',
    )
    user = models.CharField('实际使用人', max_length=50, blank=True)
    status = models.CharField('使用状态', max_length=20, choices=STATUS_CHOICES, default='库存')
    price = models.DecimalField('资产价值(元)', max_digits=12, decimal_places=2, default=0)
    purchase_date = models.DateField('购置日期', null=True, blank=True)
    location = models.CharField('存放位置', max_length=120, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '资产'
        verbose_name_plural = '资产'
        ordering = ['asset_id']

    def __str__(self):
        return f'{self.asset_id} - {self.name}'


class Requisition(models.Model):
    """资产领用 —— 借用/归还记录。

    存储状态(status)只有两态：借出 / 已归还。
    「逾期」不再入库，而是由 display_status 依据 due_date 动态推导，
    从而让仪表盘、列表页、统计使用同一种口径，避免脏数据与误回收资产。
    """
    STATUS_CHOICES = [
        ('借出', '借出'),
        ('已归还', '已归还'),
    ]

    asset = models.ForeignKey(
        Asset,
        verbose_name='资产',
        on_delete=models.CASCADE,
        related_name='requisitions',
    )
    user = models.CharField('领用人', max_length=50)
    department = models.ForeignKey(
        Department,
        verbose_name='领用部门',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='requisitions',
    )
    purpose = models.CharField('领用用途', max_length=200, blank=True)
    borrow_date = models.DateField('领用日期', auto_now_add=True)
    due_date = models.DateField('预计归还', null=True, blank=True)
    return_date = models.DateField('归还日期', null=True, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='借出')

    class Meta:
        verbose_name = '资产领用'
        verbose_name_plural = '资产领用'
        ordering = ['-borrow_date']

    def __str__(self):
        return f'{self.asset} 领用于 {self.user}'

    @property
    def is_overdue(self):
        """是否逾期：借出 且 超过预计归还日期（含当日未还）。"""
        from django.utils import timezone
        return bool(
            self.status == '借出'
            and self.due_date
            and self.due_date < timezone.localdate()
        )

    @property
    def display_status(self):
        """业务展示状态：借出（正常）/ 已归还 / 逾期（借出且过期）。"""
        return '逾期' if self.is_overdue else self.status

    def save(self, *args, **kwargs):
        """同步资产状态（置于同一事务，避免半套状态）。

        - 借出  → 资产置为「借出」
        - 已归还 → 若该资产已无其它未归还领用，则回到「库存」
        - 逾期为派生状态，绝不入库、也不触发资产回收：
          逾期中的资产仍视为占用中，应保持「借出」。
        """
        from django.db import transaction

        with transaction.atomic():
            new_status = self.status
            old_status = None
            if self.pk:
                old_status = Requisition.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            super().save(*args, **kwargs)

            if new_status == '借出':
                if self.asset.status != '借出':
                    Asset.objects.filter(pk=self.asset_id).update(status='借出')
                    self.asset.status = '借出'
            elif new_status == '已归还':
                # 只有真正处于借出(含逾期)状态的资产，在全部归还后才复原为库存
                has_outstanding = Requisition.objects.filter(
                    asset=self.asset, status='借出'
                ).exclude(pk=self.pk).exists()
                if not has_outstanding and self.asset.status in ('借出',):
                    Asset.objects.filter(pk=self.asset_id).update(status='库存')
                    self.asset.status = '库存'
            # 其余情况（老数据若存在 '逾期' 存储值）一律迁移为借出口径，不回收资产


class AssetChange(models.Model):
    """资产变更 —— 部门转移 / 状态变更。"""
    CHANGE_TYPES = [
        ('部门转移', '部门转移'),
        ('状态变更', '状态变更'),
    ]

    asset = models.ForeignKey(
        Asset,
        verbose_name='资产',
        on_delete=models.CASCADE,
        related_name='changes',
    )
    change_type = models.CharField('变更类型', max_length=20, choices=CHANGE_TYPES, default='部门转移')
    reason = models.CharField('变更原因', max_length=200, blank=True)
    old_value = models.CharField('变更前', max_length=200, blank=True)
    new_value = models.CharField('变更后', max_length=200, blank=True)
    changed_by = models.CharField('经办人', max_length=50, blank=True)
    change_date = models.DateTimeField('变更时间', auto_now_add=True)
    note = models.CharField('备注', max_length=200, blank=True)

    class Meta:
        verbose_name = '资产变更'
        verbose_name_plural = '资产变更'
        ordering = ['-change_date']

    def __str__(self):
        return f'{self.asset} {self.change_type}'
