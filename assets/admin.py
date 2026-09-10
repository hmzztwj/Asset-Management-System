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
from .models import Department, Asset, Requisition, AssetChange, BackupSetting


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
    list_display = ('asset', 'user', 'borrow_date', 'return_date', 'status')
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
    """

    change_list_template = 'admin/assets/backupsetting/change_list.html'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
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
        return self._redirect()

    def backup_download(self, request, name):
        path = os.path.join(backup.get_backup_dir(), os.path.basename(name))
        if not os.path.exists(path):
            raise Http404('备份文件不存在')
        return FileResponse(open(path, 'rb'), as_attachment=True,
                            filename=os.path.basename(name))

    def backup_restore(self, request, name):
        if request.method == 'POST':
            try:
                backup.restore_backup(name)
                messages.success(
                    request,
                    f'已从备份「{name}」恢复。恢复前的数据已自动另存为一份新备份；'
                    f'若登录状态失效请重新登录。',
                )
            except Exception as exc:  # noqa: BLE001
                messages.error(request, f'恢复失败：{exc}')
        return self._redirect()

    def backup_delete(self, request, name):
        if request.method == 'POST':
            path = os.path.join(backup.get_backup_dir(), os.path.basename(name))
            if os.path.exists(path):
                os.remove(path)
                messages.success(request, f'已删除备份「{name}」')
        return self._redirect()


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
