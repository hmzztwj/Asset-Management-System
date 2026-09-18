from datetime import time as _time

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
    email_notify = models.BooleanField(
        '邮箱通知', default=False,
        help_text='勾选后，该角色下的账号（填了邮箱的）会收到逾期提醒等通知邮件',
    )
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
            'manage_users', 'email_notify',
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
    is_builtin = models.BooleanField(
        '系统内置账号', default=False,
        help_text='内置账号不可删除、停用或降级，用于避免系统被锁死',
    )
    session_key = models.CharField(
        '当前登录会话', max_length=64, blank=True, default='',
        help_text='记录该账号最近一次登录的会话；普通账号仅允许一台设备在线，超管不受限',
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

    # 资产归还后回到综合管理部，责任人与实际使用人统一落到资产管理员。
    DEFAULT_OWNER = '资产管理员'
    DEFAULT_DEPT_NAME = '综合管理部'

    asset = models.ForeignKey(
        Asset,
        verbose_name='资产',
        on_delete=models.CASCADE,
        related_name='requisitions',
    )
    user = models.CharField('领用人', max_length=50)
    actual_user = models.CharField(
        '实际使用人', max_length=50, blank=True,
        help_text='选填；留空表示实际使用人同领用人',
    )
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

    @property
    def effective_user(self):
        """实际使用人；留空时视为与领用人一致。"""
        return (self.actual_user or '').strip() or self.user

    @classmethod
    def default_department(cls):
        """归还后资产应归属的部门（综合管理部）；不存在时返回 None。"""
        return Department.objects.filter(name=cls.DEFAULT_DEPT_NAME).first()

    def _sync_asset_on_borrow(self):
        """借出：资产置为「借出」，责任人→领用人，实际使用人→表单值，部门→领用部门。"""
        fields = {
            'status': '借出',
            'responsible': self.user or '',
            'user': self.effective_user or '',
        }
        # 所属部门随领用部门流转；未选部门时保持原值，避免误清空
        if self.department_id:
            fields['department_id'] = self.department_id
        Asset.objects.filter(pk=self.asset_id).update(**fields)

    def _sync_asset_on_return(self):
        """归还：资产回「库存」，责任人 / 实际使用人→资产管理员，部门→综合管理部。"""
        fields = {
            'status': '库存',
            'responsible': self.DEFAULT_OWNER,
            'user': self.DEFAULT_OWNER,
        }
        default_dept = self.default_department()
        if default_dept:
            fields['department_id'] = default_dept.pk
        Asset.objects.filter(pk=self.asset_id).update(**fields)

    def save(self, *args, **kwargs):
        """同步资产状态与人员归属（置于同一事务，避免半套状态）。

        - 借出  → 资产「借出」，责任人=领用人、实际使用人=实际使用人、部门=领用部门
        - 已归还 → 若无其它未归还领用，资产回「库存」，
                   责任人 / 实际使用人=资产管理员、部门=综合管理部
        - 逾期为派生状态，绝不入库、也不触发资产回收：
          逾期中的资产仍视为占用中，应保持「借出」。
        """
        from django.db import transaction

        with transaction.atomic():
            new_status = self.status
            super().save(*args, **kwargs)

            if new_status == '借出':
                self._sync_asset_on_borrow()
                self.asset.refresh_from_db()
            elif new_status == '已归还':
                # 只有真正处于借出(含逾期)状态的资产，在全部归还后才复原为库存
                has_outstanding = Requisition.objects.filter(
                    asset=self.asset, status='借出'
                ).exclude(pk=self.pk).exists()
                if not has_outstanding and self.asset.status in ('借出',):
                    self._sync_asset_on_return()
                    self.asset.refresh_from_db()
            # 其余情况（老数据若存在 '逾期' 存储值）一律迁移为借出口径，不回收资产

    def delete(self, *args, **kwargs):
        """删除领用记录：若该资产已无其它未归还领用，则复位为库存 + 默认归属。

        删除不走 save()，因此这里显式处理，保证无论从页面、后台还是脚本删除，
        资产都不会残留「借出 + 借用人」的脏状态。
        """
        from django.db import transaction

        asset = self.asset
        with transaction.atomic():
            super().delete(*args, **kwargs)
            has_outstanding = Requisition.objects.filter(
                asset=asset, status='借出'
            ).exists()
            if has_outstanding:
                return
            asset.refresh_from_db()
            if asset.status != '借出':
                return
            fields = {
                'status': '库存',
                'responsible': self.DEFAULT_OWNER,
                'user': self.DEFAULT_OWNER,
            }
            default_dept = self.default_department()
            if default_dept:
                fields['department_id'] = default_dept.pk
            Asset.objects.filter(pk=asset.pk).update(**fields)


class EmailConfig(models.Model):
    """邮件提醒配置（单条记录，pk 固定为 1）。

    * 填写并启用后，每天 ``send_hour`` 点由计划任务调用
      ``manage.py send_overdue_digest`` 发送逾期领用汇总给管理员；
    * 未启用（或后台未填、环境变量也没有）时功能静默关闭；
    * SMTP 密码加密存储（见 assets/mailconf.py 的 seal/unseal）。
    """
    enabled = models.BooleanField('启用邮件提醒', default=False)
    smtp_host = models.CharField('SMTP 服务器', max_length=100, blank=True,
                                 help_text='如 smtp.exmail.qq.com')
    smtp_port = models.PositiveIntegerField('SMTP 端口', default=465)
    use_ssl = models.BooleanField('使用 SSL', default=True,
                                  help_text='端口 465 勾选；587 端口不勾（改用 STARTTLS）')
    smtp_user = models.CharField('SMTP 账号', max_length=100, blank=True,
                                 help_text='通常是发件邮箱地址')
    smtp_password = models.CharField('SMTP 密码/授权码', max_length=300, blank=True,
                                     help_text='加密存储；后台展示为打码')
    from_email = models.CharField('发件人地址', max_length=100, blank=True,
                                  help_text='留空则使用 SMTP 账号')
    send_hour = models.PositiveIntegerField('每日发送时间（小时 0-23）', default=9)
    last_sent_at = models.DateTimeField('上次发送时间', null=True, blank=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '邮箱配置'
        verbose_name_plural = '邮箱配置'

    def __str__(self):
        return f'邮箱配置（{"启用" if self.enabled else "停用"}）'

    def save(self, *args, **kwargs):
        self.pk = 1  # 单例：永远只有一条配置
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def smtp_params(self):
        """后台配置可用则返回 SMTP 参数字典，否则 None（由环境变量兜底）。"""
        from . import mailconf
        if not (self.enabled and self.smtp_host and self.smtp_user):
            return None
        return {
            'host': self.smtp_host,
            'port': self.smtp_port,
            'use_ssl': self.use_ssl,
            'username': self.smtp_user,
            'password': mailconf.unseal_password(self.smtp_password),
            'from_email': self.from_email or self.smtp_user,
        }


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
    # 部门转移可连带记录责任人 / 实际使用人的变动（留空表示不变）
    old_responsible = models.CharField('变更前责任人', max_length=50, blank=True)
    old_user = models.CharField('变更前实际使用人', max_length=50, blank=True)
    new_responsible = models.CharField('变更后责任人', max_length=50, blank=True)
    new_user = models.CharField('变更后实际使用人', max_length=50, blank=True)
    changed_by = models.CharField('经办人', max_length=50, blank=True)
    change_date = models.DateTimeField('变更时间', auto_now_add=True)
    note = models.CharField('备注', max_length=200, blank=True)

    class Meta:
        verbose_name = '资产变更'
        verbose_name_plural = '资产变更'
        ordering = ['-change_date']

    def __str__(self):
        return f'{self.asset} {self.change_type}'


class BackupSetting(models.Model):
    """数据备份设置（单例）。

    只用于保存"是否自动备份 / 自动备份频率 / 备份目录 / 上次备份时间"。
    备份文件本身为整库 .sqlite3 快照，由 assets/backup.py 负责生成与管理。
    """
    INTERVAL_CHOICES = [
        ('daily', '每天定时'),
        ('3d', '每隔 3 天'),
        ('7d', '每隔 7 天'),
        ('on_change', '每次数据变动'),
    ]

    auto_enabled = models.BooleanField('启用自动备份', default=False)
    interval = models.CharField('自动备份频率', max_length=20, choices=INTERVAL_CHOICES, default='daily')
    schedule_time = models.TimeField(
        '定时备份时间', default=_time(22, 0),
        help_text='到达该时刻后的第一次访问（含浏览页面）即触发备份，无需写入操作',
    )
    backup_dir = models.CharField(
        '备份目录', max_length=255, default='backup',
        help_text='相对项目根目录即可（默认 backup）；也可填绝对路径',
    )
    last_backup_at = models.DateTimeField('上次备份时间', null=True, blank=True)

    class Meta:
        verbose_name = '数据备份'
        verbose_name_plural = '数据备份'

    def __str__(self):
        return '数据备份设置'

    def save(self, *args, **kwargs):
        self.pk = 1  # 强制单例
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """获取（或创建）唯一的设置记录。"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AssetAttachment(models.Model):
    """资产附件 —— 发票、实物照片、验收单等留证材料。

    文件物理存放在 MEDIA_ROOT 下（默认 data/media/attachments/YYYY/MM/），
    下载统一走受登录与权限保护的视图（views.attachment_download），
    不直接暴露媒体目录，避免附件被匿名下载。
    """
    # 允许的附件后缀（小写，含点）与单文件大小上限
    ALLOWED_EXT = (
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.zip', '.rar', '.7z',
    )
    MAX_SIZE = 20 * 1024 * 1024  # 20 MB

    asset = models.ForeignKey(
        Asset, verbose_name='资产', on_delete=models.CASCADE, related_name='attachments',
    )
    file = models.FileField('文件', upload_to='attachments/%Y/%m/')
    name = models.CharField('文件名', max_length=200, blank=True)
    note = models.CharField('备注', max_length=200, blank=True)
    size = models.PositiveIntegerField('文件大小(字节)', default=0)
    uploaded_by = models.CharField('上传人', max_length=50, blank=True)
    uploaded_at = models.DateTimeField('上传时间', auto_now_add=True)

    class Meta:
        verbose_name = '资产附件'
        verbose_name_plural = '资产附件'
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.name or (self.file.name if self.file else '附件')

    @property
    def size_h(self):
        """可读的文件大小。"""
        num = float(self.size or 0)
        if num < 1024:
            return f'{int(num)} B'
        for unit in ('KB', 'MB', 'GB'):
            num /= 1024.0
            if num < 1024 or unit == 'GB':
                return f'{num:.1f} {unit}'
        return f'{num:.1f} GB'


class OperationLog(models.Model):
    """全局操作日志 —— 记录"谁在什么时候对什么做了什么"。

    覆盖：登录成功/失败、资产增删改（含字段级变更明细）、领用、变更、
    组织架构、用户/角色、备份生成/恢复/删除、附件上传删除。

    写入统一走 assets/oplog.py 的 log()，该函数吞掉所有异常，
    保证日志失败绝不影响主业务流程。
    """
    CATEGORY_CHOICES = [
        ('auth', '登录认证'),
        ('asset', '资产库'),
        ('requisition', '资产领用'),
        ('change', '资产变更'),
        ('org', '组织架构'),
        ('user', '用户/角色'),
        ('backup', '数据备份'),
        ('attachment', '资产附件'),
    ]
    ACTION_CHOICES = [
        ('login', '登录成功'),
        ('login_fail', '登录失败'),
        ('logout', '退出登录'),
        ('create', '新增'),
        ('update', '修改'),
        ('delete', '删除'),
        ('import', '批量导入'),
        ('backup', '生成备份'),
        ('restore', '恢复备份'),
        ('download', '下载'),
        ('other', '其它'),
    ]

    created_at = models.DateTimeField('时间', auto_now_add=True, db_index=True)
    category = models.CharField('模块', max_length=20, choices=CATEGORY_CHOICES, db_index=True)
    action = models.CharField('动作', max_length=20, choices=ACTION_CHOICES, db_index=True)
    target = models.CharField('操作对象', max_length=200, blank=True)
    detail = models.TextField('详情', blank=True)
    operator = models.CharField('操作人', max_length=50, blank=True, db_index=True)
    ip = models.CharField('来源 IP', max_length=45, blank=True)

    class Meta:
        verbose_name = '操作日志'
        verbose_name_plural = '操作日志'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['-created_at', 'category'])]

    def __str__(self):
        return f'[{self.get_category_display()}] {self.get_action_display()} {self.target}'
