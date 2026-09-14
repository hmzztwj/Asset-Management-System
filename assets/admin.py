import os
from datetime import time as _time

from django.contrib import admin, messages
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import path

from . import backup
from . import oplog
from .models import (
    Department, Asset, Requisition, AssetChange, BackupSetting,
    AssetAttachment, OperationLog,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'manager', 'created_at')
    list_filter = ('parent',)
    search_fields = ('name', 'manager')


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ('asset_id', 'name', 'category', 'department', 'responsible', 'user', 'serial', 'status', 'price')
    list_filter = ('status', 'category', 'department')
    search_fields = ('asset_id', 'name', 'serial', 'responsible', 'user')


@admin.register(Requisition)
class RequisitionAdmin(admin.ModelAdmin):
    list_display = ('asset', 'user', 'actual_user', 'borrow_date', 'return_date', 'status')
    list_filter = ('status',)
    search_fields = ('user', 'asset__name')


@admin.register(AssetChange)
class AssetChangeAdmin(admin.ModelAdmin):
    list_display = ('asset', 'change_type', 'old_value', 'new_value', 'changed_by', 'change_date')
    list_filter = ('change_type',)
    search_fields = ('asset__name', 'changed_by')


@admin.register(BackupSetting)
class BackupSettingAdmin(admin.ModelAdmin):
    """数据备份管理页。

    changelist 被替换为自定义页面：手动备份、自动备份开关/频率、备份文件列表
    （下载 / 恢复 / 删除）。备份为整库 .sqlite3 快照，详见 assets/backup.py。

    权限口径：
    - 「恢复」「下载」属于破坏性 / 敏感操作，**仅超级管理员**可执行。
      其中恢复还要求手工输入确认口令 RESTORE，防止误点一键回滚整库。
    - 生成备份、查看列表不设限（管理员即可）。
    """

    change_list_template = 'admin/assets/backupsetting/change_list.html'

    # 恢复整库必须输入的确认口令
    RESTORE_CONFIRM_WORD = 'RESTORE'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True

    # ---------- 权限辅助 ----------
    def _require_superuser(self, request, action_label):
        """非超管执行敏感操作时给出提示并拒绝。返回 True 表示已放行。"""
        if request.user.is_superuser:
            return True
        messages.error(request, f'仅超级管理员可{action_label}，请联系系统管理员。')
        oplog.log(
            request, 'backup', 'other',
            target=action_label,
            detail='越权尝试：非超级管理员请求敏感备份操作，已拒绝',
        )
        return False

    # ---------- 自定义路由 ----------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('backup-now/', self.admin_site.admin_view(self.backup_now), name='backup_now'),
            path('save-settings/', self.admin_site.admin_view(self.save_settings), name='backup_save_settings'),
            path('download/<str:name>/', self.admin_site.admin_view(self.backup_download), name='backup_download'),
            path('restore/<str:name>/', self.admin_site.admin_view(self.backup_restore), name='backup_restore'),
            path('delete/<str:name>/', self.admin_site.admin_view(self.backup_delete), name='backup_delete'),
        ]
        return custom + urls

    def changelist_view(self, request, extra_context=None):
        setting = BackupSetting.get_solo()
        files = backup.list_backups()
        for f in files:
            f['size_h'] = backup.human_size(f['size'])

        extra_context = extra_context or {}
        extra_context.update({
            'title': '数据备份',
            'setting': setting,
            'backups': files,
            'backup_dir': backup.get_backup_dir(),
            'max_backups': backup.MAX_BACKUPS,
            'interval_choices': BackupSetting.INTERVAL_CHOICES,
            # 模板据此隐藏/禁用「下载」「恢复」按钮
            'can_sensitive': bool(request.user.is_superuser),
            'restore_word': self.RESTORE_CONFIRM_WORD,
        })
        return super().changelist_view(request, extra_context=extra_context)

    # ---------- 动作 ----------
    def _redirect(self):
        return redirect('admin:assets_backupsetting_changelist')

    def backup_now(self, request):
        if request.method == 'POST':
            try:
                fname, _ = backup.create_backup(reason='manual')
                messages.success(request, f'备份成功：{fname}')
                oplog.log(request, 'backup', 'backup', target=fname, detail='手动生成整库备份')
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f'备份失败：{exc}')
        return self._redirect()

    def save_settings(self, request):
        if request.method == 'POST':
            setting = BackupSetting.get_solo()
            setting.auto_enabled = request.POST.get('auto_enabled') == 'on'
            interval = request.POST.get('interval')
            if interval in dict(BackupSetting.INTERVAL_CHOICES):
                setting.interval = interval
            raw_time = (request.POST.get('schedule_time') or '').strip()
            if raw_time:
                try:
                    hh, mm = raw_time.split(':')[:2]
                    setting.schedule_time = _time(int(hh), int(mm))
                except (ValueError, TypeError):
                    messages.warning(request, '备份时间格式不正确，已保留原设置')
            backup_dir = (request.POST.get('backup_dir') or 'backup').strip()
            setting.backup_dir = backup_dir or 'backup'
            setting.save()
            messages.success(request, '备份设置已保存')
            oplog.log(
                request, 'backup', 'update', target='备份设置',
                detail=(f'自动备份={"开" if setting.auto_enabled else "关"}；'
                        f'频率={setting.get_interval_display()}；'
                        f'定时={setting.schedule_time}；目录={setting.backup_dir}'),
            )
        return self._redirect()

    def backup_download(self, request, name):
        # 备份文件含全部账号密码哈希，下载仅限超级管理员
        if not self._require_superuser(request, '下载数据库备份'):
            return self._redirect()
        path = os.path.join(backup.get_backup_dir(), os.path.basename(name))
        if not os.path.exists(path):
            raise Http404('备份文件不存在')
        oplog.log(request, 'backup', 'download', target=os.path.basename(name), detail='下载整库备份文件')
        return FileResponse(open(path, 'rb'), as_attachment=True,
                            filename=os.path.basename(name))

    def backup_restore(self, request, name):
        if request.method == 'POST':
            # 双保险：仅超管 + 必须手工输入确认口令
            if not self._require_superuser(request, '恢复数据库备份'):
                return self._redirect()
            typed = (request.POST.get('confirm_word') or '').strip()
            if typed != self.RESTORE_CONFIRM_WORD:
                messages.error(
                    request,
                    f'恢复未执行：请在确认框中输入 {self.RESTORE_CONFIRM_WORD} 以示确认。',
                )
                return self._redirect()
            try:
                backup.restore_backup(name)
                messages.success(
                    request,
                    f'已从备份「{name}」恢复。恢复前的数据已自动另存为一份新备份；'
                    f'若登录状态失效请重新登录。',
                )
                oplog.log(request, 'backup', 'restore', target=name, detail='从备份恢复整库')
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f'恢复失败：{exc}')
        return self._redirect()

    def backup_delete(self, request, name):
        if request.method == 'POST':
            path = os.path.join(backup.get_backup_dir(), os.path.basename(name))
            if os.path.exists(path):
                os.remove(path)
                messages.success(request, f'已删除备份「{name}」')
                oplog.log(request, 'backup', 'delete', target=os.path.basename(name), detail='删除备份文件')
        return self._redirect()


@admin.register(AssetAttachment)
class AssetAttachmentAdmin(admin.ModelAdmin):
    """附件列表：可在后台查看与删除，但不允许在此新增（新增走资产编辑页）。"""

    list_display = ('name', 'asset', 'size_h', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)
    search_fields = ('name', 'asset__asset_id', 'asset__name', 'uploaded_by')
    readonly_fields = ('asset', 'file', 'name', 'note', 'size', 'uploaded_by', 'uploaded_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OperationLog)
class OperationLogAdmin(admin.ModelAdmin):
    """操作日志：**只读**查看，可按模块/动作/时间筛选与搜索。"""

    list_display = ('created_at', 'category', 'action', 'operator', 'target', 'ip')
    list_filter = ('category', 'action')
    search_fields = ('operator', 'target', 'detail', 'ip')
    date_hierarchy = 'created_at'
    list_per_page = 50
    readonly_fields = ('created_at', 'category', 'action', 'target', 'detail', 'operator', 'ip')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # 只读：允许查看列表与详情，但不允许编辑
        return False

    def has_delete_permission(self, request, obj=None):
        # 仅超级管理员可清理日志
        return bool(request.user.is_superuser)


# Django 自带后台的用户管理同步加保护，避免从 /admin/auth/user/ 绕过删除内置账号
try:
    admin.site.unregister(User)
except NotRegistered:
    pass


@admin.register(User)
class ProtectedUserAdmin(BaseUserAdmin):
    """保护内置账号：后台不允许删除（含批量删除动作）。"""

    @staticmethod
    def _is_builtin(obj):
        return bool(getattr(getattr(obj, 'profile', None), 'is_builtin', False))

    def has_delete_permission(self, request, obj=None):
        if obj is not None and self._is_builtin(obj):
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request, obj):
        if self._is_builtin(obj):
            self.message_user(request, '内置账号不可删除。', level=messages.WARNING)
            return
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        builtins = queryset.filter(profile__is_builtin=True)
        if builtins.exists():
            self.message_user(request, '内置账号不可删除，已自动跳过。', level=messages.WARNING)
        super().delete_queryset(request, queryset.exclude(profile__is_builtin=True))
