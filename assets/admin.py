from django.contrib import admin
from .models import Department, Asset, Requisition, AssetChange


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
