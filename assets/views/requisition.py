"""资产领用：列表 / 导出 / 领用 / 归还 / 编辑 / 删除（联动在模型层）。"""

from openpyxl import Workbook

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .. import oplog
from ..models import Asset, Department, Requisition
from ..permissions import perm_required
from .common import _asset_label, _parse_date

@perm_required('view_requisition')
def requisition(request):
    status = request.GET.get('status', '')

    all_records = list(Requisition.objects.select_related('asset', 'department').order_by('-borrow_date'))
    if status == '逾期':
        records = [r for r in all_records if r.display_status == '逾期']
    elif status:
        records = [r for r in all_records if r.status == status]
    else:
        records = all_records

    overdue_count = sum(1 for r in all_records if r.display_status == '逾期')

    paginator = Paginator(records, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    available_assets = Asset.objects.filter(status='库存')
    asset_options = [
        {'id': a.pk, 'asset_id': a.asset_id, 'name': a.name, 'status': a.status}
        for a in available_assets
    ]

    context = {
        'records': page_obj.object_list,
        'page_obj': page_obj,
        'assets': available_assets,
        'asset_options': asset_options,
        'department_options': [{'id': d.id, 'text': d.name} for d in Department.objects.all()],
        'departments': Department.objects.all(),
        'total_borrowed': Requisition.objects.filter(status='借出').count(),
        'total_returned': Requisition.objects.filter(status='已归还').count(),
        'overdue_count': overdue_count,
        'status': status,
        'page_title': '资产领用',
        'active': 'requisition',
    }
    return render(request, 'requisition.html', context)


@perm_required('view_requisition')
def requisition_export(request):
    """按当前筛选条件导出「资产领用」记录为 Excel。"""
    status = request.GET.get('status', '')
    all_records = list(Requisition.objects.select_related('asset', 'department').order_by('-borrow_date'))
    if status == '逾期':
        records = [r for r in all_records if r.display_status == '逾期']
    elif status:
        records = [r for r in all_records if r.status == status]
    else:
        records = all_records

    wb = Workbook()
    ws = wb.active
    ws.title = '资产领用'
    headers = ['资产编号', '资产名称', '领用人', '实际使用人', '领用部门', '领用用途',
               '领用日期', '预计归还', '归还日期', '状态']
    ws.append(headers)
    for r in records:
        ws.append([
            r.asset.asset_id,
            r.asset.name,
            r.user,
            r.actual_user or '',
            r.department.name if r.department else '',
            r.purpose,
            r.borrow_date.strftime('%Y-%m-%d') if r.borrow_date else '',
            r.due_date.strftime('%Y-%m-%d') if r.due_date else '',
            r.return_date.strftime('%Y-%m-%d') if r.return_date else '',
            r.display_status,
        ])
    for i, w in enumerate([14, 22, 12, 14, 14, 24, 12, 12, 12, 10], start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="requisition_export.xlsx"'
    wb.save(response)
    return response


@perm_required('manage_requisition')
def requisition_create(request):
    if request.method == 'POST':
        asset_id = request.POST.get('asset')
        user = request.POST.get('user', '').strip()
        actual_user = request.POST.get('actual_user', '').strip()
        department_id = request.POST.get('department') or None
        purpose = request.POST.get('purpose', '').strip()
        due_raw = (request.POST.get('due_date') or '').strip()
        due_date = _parse_date(due_raw) if due_raw else None

        if not asset_id:
            messages.error(request, '请选择要领用的资产。')
        elif not user:
            messages.error(request, '领用人不能为空。')
        elif not department_id:
            messages.error(request, '请选择领用部门。')
        elif not due_raw:
            messages.error(request, '请选择预计归还日期。')
        elif due_date is None:
            messages.error(request, '预计归还日期格式不正确，应为 YYYY-MM-DD。')
        elif not purpose:
            messages.error(request, '请填写领用用途。')
        else:
            asset = get_object_or_404(Asset, pk=asset_id)
            if asset.status not in ['库存', '维修']:
                messages.error(request, f'资产 {asset.name} 当前状态为「{asset.status}」，不可领用。')
            else:
                Requisition.objects.create(
                    asset=asset, user=user, actual_user=actual_user,
                    department_id=department_id,
                    purpose=purpose, due_date=due_date,
                )
                oplog.log(
                    request, 'requisition', 'create', target=_asset_label(asset),
                    detail=(f'领用人：{user}；实际使用人：{actual_user or "同领用人"}；'
                            f'预计归还：{due_date}；用途：{purpose}'),
                )
                messages.success(
                    request,
                    f'资产 {asset.name} 已领用给 {user}，责任人、实际使用人与所属部门已同步到资产库。',
                )
                return redirect('requisition')
    return redirect('requisition')


@perm_required('manage_requisition')
def requisition_return(request, pk):
    record = get_object_or_404(Requisition, pk=pk)
    if request.method == 'POST':
        from django.db import transaction
        with transaction.atomic():
            record.status = '已归还'
            record.return_date = timezone.localdate()
            record.save()
        oplog.log(request, 'requisition', 'update', target=_asset_label(record.asset),
                  detail=(f'归还登记：领用人 {record.user}；归还日期 {record.return_date}；'
                          f'资产责任人/实际使用人已复位为「{Requisition.DEFAULT_OWNER}」'))
        messages.success(request, f'资产 {record.asset.name} 已归还。')
    return redirect('requisition')


@perm_required('manage_requisition')
def requisition_edit(request, pk):
    record = get_object_or_404(Requisition, pk=pk)
    if request.method == 'POST':
        before = {
            'user': record.user, 'actual_user': record.actual_user,
            'department': record.department.name if record.department_id else '',
            'purpose': record.purpose,
            'due_date': record.due_date.strftime('%Y-%m-%d') if record.due_date else '',
            'status': record.status,
        }
        record.user = request.POST.get('user', record.user).strip()
        record.actual_user = request.POST.get('actual_user', record.actual_user).strip()
        record.department_id = request.POST.get('department') or None
        record.purpose = request.POST.get('purpose', '').strip()
        # 日期必须真正解析成 date 对象：直接把表单字符串赋给 DateField，
        # SQLite 能存进去，但后续 strftime / 日期比较会以 str 报 500
        due_raw = (request.POST.get('due_date') or '').strip()
        return_raw = (request.POST.get('return_date') or '').strip()
        record.due_date = _parse_date(due_raw) if due_raw else None
        record.return_date = _parse_date(return_raw) if return_raw else None
        # 状态归一化：存储态仅「借出/已归还」；逾期为派生状态，不允许手工入库
        raw_status = request.POST.get('status', '')
        record.status = '已归还' if raw_status == '已归还' else '借出'
        if not record.user:
            messages.error(request, '领用人不能为空。')
        elif not record.department_id:
            messages.error(request, '请选择领用部门。')
        elif not record.purpose:
            messages.error(request, '请填写领用用途。')
        elif not due_raw:
            messages.error(request, '请选择预计归还日期。')
        elif record.due_date is None:
            messages.error(request, '预计归还日期格式不正确，应为 YYYY-MM-DD。')
        elif return_raw and record.return_date is None:
            messages.error(request, '归还日期格式不正确，应为 YYYY-MM-DD。')
        else:
            record.save()
            after = {
                'user': record.user, 'actual_user': record.actual_user,
                'department': record.department.name if record.department_id else '',
                'purpose': record.purpose,
                'due_date': record.due_date.strftime('%Y-%m-%d') if record.due_date else '',
                'status': record.status,
            }
            diff_text = oplog.diff(before, after, {
                'user': '领用人', 'actual_user': '实际使用人', 'department': '领用部门',
                'purpose': '领用用途', 'due_date': '预计归还', 'status': '状态',
            })
            if diff_text:
                oplog.log(request, 'requisition', 'update',
                          target=_asset_label(record.asset), detail=diff_text)
            messages.success(request, '领用记录已更新。')
        return redirect('requisition')
    context = {
        'record': record,
        'departments': Department.objects.all(),
        'page_title': '编辑领用',
        'active': 'requisition',
    }
    return render(request, 'requisition_form.html', context)


@perm_required('manage_requisition')
def requisition_delete(request, pk):
    record = get_object_or_404(Requisition, pk=pk)
    if request.method == 'POST':
        from django.db import transaction
        with transaction.atomic():
            # 复位资产状态与归属的逻辑在 Requisition.delete() 中统一处理
            target = _asset_label(record.asset)
            detail = f'删除领用记录（领用人：{record.user}；状态：{record.display_status}）'
            record.delete()
        oplog.log(request, 'requisition', 'delete', target=target, detail=detail)
        messages.success(request, '领用记录已删除。')
    return redirect('requisition')

