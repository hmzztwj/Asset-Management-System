from django.urls import path
from . import views

urlpatterns = [
    # 登录 / 退出
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password/change/', views.password_change, name='password_change'),

    # 首页仪表盘
    path('', views.dashboard, name='dashboard'),

    # 资产库
    path('library/', views.library, name='library'),
    path('library/add/', views.asset_create, name='asset_create'),
    path('library/labels/', views.asset_labels, name='asset_labels'),
    path('library/<int:pk>/edit/', views.asset_update, name='asset_update'),
    path('library/<int:pk>/qr/', views.asset_qr, name='asset_qr'),
    path('library/<int:pk>/delete/', views.asset_delete, name='asset_delete'),
    path('library/bulk-delete/', views.assets_bulk_delete, name='assets_bulk_delete'),
    path('library/import/', views.asset_import, name='asset_import'),
    path('library/import/template/', views.asset_import_template, name='asset_import_template'),

    # 资产附件
    path('library/<int:pk>/attachments/upload/', views.attachment_upload, name='attachment_upload'),
    path('attachments/<int:pk>/download/', views.attachment_download, name='attachment_download'),
    path('attachments/<int:pk>/delete/', views.attachment_delete, name='attachment_delete'),

    # 组织架构
    path('org/', views.org, name='org'),
    path('org/add/', views.department_form, name='department_create'),
    path('org/<int:pk>/edit/', views.department_form, name='department_update'),
    path('org/<int:pk>/delete/', views.department_delete, name='department_delete'),

    # 资产领用
    path('requisition/', views.requisition, name='requisition'),
    path('requisition/export/', views.requisition_export, name='requisition_export'),
    path('requisition/add/', views.requisition_create, name='requisition_create'),
    path('requisition/<int:pk>/return/', views.requisition_return, name='requisition_return'),
    path('requisition/<int:pk>/edit/', views.requisition_edit, name='requisition_edit'),
    path('requisition/<int:pk>/delete/', views.requisition_delete, name='requisition_delete'),

    # 资产变更
    path('change/', views.change, name='change'),
    path('change/export/', views.change_export, name='change_export'),
    path('change/add/', views.change_create, name='change_create'),
    path('change/<int:pk>/edit/', views.change_update, name='change_update'),
    path('change/<int:pk>/delete/', views.change_delete, name='change_delete'),

    # 用户管理（仅管理员）
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_update, name='user_update'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),

    # 角色管理（仅管理员）
    path('roles/', views.role_list, name='role_list'),
    path('roles/add/', views.role_create, name='role_create'),
    path('roles/<int:pk>/edit/', views.role_update, name='role_update'),
    path('roles/<int:pk>/delete/', views.role_delete, name='role_delete'),

    # 操作日志（仅管理员）
    path('oplogs/', views.oplog_list, name='oplog_list'),
]
