"""资产变更：列表 / 导出 / 变更登记（含台账同步）与编辑删除。"""

from openpyxl import Workbook

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .. import oplog
from ..models import Asset, AssetChange, Department
from ..permissions import perm_required
from .common import _asset_label

@perm_required('view_change')
def change(request):
    ctype = request.GET.get('type', '')
    records = AssetChange.objects.select_related('asset').order_by('-change_date')
    if ctype:
        records = records.filter(change_type=ctype)

    paginator = Paginator(records, 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    all_assets = Asset.objects.all()
    asset_options = [
        {'id': a.pk, 'asset_id': a.asset_id, 'name': a.name, 'status': a.status,
         'department': a.department.name if a.department else '',
         'responsible': a.responsible or '', 'user': a.user or ''}
        for a in all_assets
    ]

    context = {
        'records': page_obj.object_list,
        'page_obj': page_obj,
        'assets': all_assets,
        'asset_options': asset_options,
        'change_type_options': [{'id': t[0], 'text': t[0]} for t in AssetChange.CHANGE_TYPES],
        'departments': Department.objects.all(),
        'ctype': ctype,
        'page_title': '资产变更',
        'active': 'change',
    }
    return render(request, 'change.html', context)


@perm_required('view_change')
def change_export(request):
    """按当前筛选条件导出「资产变更」记录为 Excel。"""
    ctype = request.GET.get('type', '')
    records = AssetChange.objects.select_related('asset').order_by('-change_date')
    if ctype:
        records = records.filter(change_type=ctype)

    wb = Workbook()
    ws = wb.active
    ws.title = '资产变更'
    headers = ['资产编号', '资产名称', '变更类型', '变更原因', '变更前',
               '变更后', '责任人（变更前→后）', '实际使用人（变更前→后）',
               '经办人', '变更时间', '备注']
    ws.append(headers)

    def _pair(old, new):
        old, new = (old or '').strip(), (new or '').strip()
        if not old and not new:
            return ''
        return f'{old or "—"} → {new or "—"}'

    for r in records:
        ws.append([
            r.asset.asset_id,
            r.asset.name,
            r.change_type,
            r.reason,
            r.old_value,
            r.new_value,
            _pair(r.old_responsible, r.new_responsible),
            _pair(r.old_user, r.new_user),
            r.changed_by,
            timezone.localtime(r.change_date).strftime('%Y-%m-%d %H:%M') if r.change_date else '',
            r.note,
        ])
    for i, w in enumerate([14, 22, 12, 22, 16, 16, 20, 20, 12, 18, 22], start=1):
        ws.column_dimensions[chr(64 + i)].width = w
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="change_export.xlsx"'
    wb.save(response)
    return response


@perm_required('manage_change')
def change_create(request):
    if request.method == 'POST':
        asset_id = request.POST.get('asset')
        change_type = request.POST.get('change_type', '部门转移')
        reason = request.POST.get('reason', '').strip()
        old_value = request.POST.get('old_value', '').strip()
        new_value = request.POST.get('new_value', '').strip()
        new_responsible = request.POST.get('new_responsible', '').strip()
        new_user = request.POST.get('new_user', '').strip()
        changed_by = request.POST.get('changed_by', '').strip()
        note = request.POST.get('note', '').strip()

        if not asset_id:
            messages.error(request, '请选择要变更的资产。')
        elif not reason:
            messages.error(request, '请填写变更原因。')
        elif not old_value:
            messages.error(request, '请填写变更前。')
        elif not new_value:
            messages.error(request, '请填写变更后。')
        elif not changed_by:
            messages.error(request, '请填写经办人。')
        else:
            asset = get_object_or_404(Asset, pk=asset_id)
            # 先校验可同步性，失败则不落库，避免产生从未生效的假变更记录
            ok, msg = _validate_change(change_type, new_value)
            if not ok:
                messages.error(request, msg)
            else:
                # 部门转移：自动记录变更前的责任人 / 实际使用人（历史快照）
                old_responsible = asset.responsible if change_type == '部门转移' else ''
                old_user = asset.user if change_type == '部门转移' else ''
                from django.db import transaction
                with transaction.atomic():
                    AssetChange.objects.create(
                        asset=asset, change_type=change_type, reason=reason,
                        old_value=old_value, new_value=new_value,
                        old_responsible=old_responsible, old_user=old_user,
                        new_responsible=new_responsible, new_user=new_user,
                        changed_by=changed_by, note=note,
                    )
                    ok2, msg2 = _apply_change_sync(
                        asset, change_type, new_value,
                        new_responsible=new_responsible, new_user=new_user,
                    )
                    if not ok2:
                        messages.warning(request, '变更记录已保存，但资产同步未完成：' + (msg2 or ''))
                    else:
                        messages.success(request, f'资产 {asset.name} 变更记录已保存，并同步到资产库。')
                    oplog.log(
                        request, 'change', 'create', target=_asset_label(asset),
                        detail=(f'{change_type}：{old_value} → {new_value}；原因：{reason}；'
                                f'经办人：{changed_by}'
                                + (f'；责任人：{old_responsible or "—"} → {new_responsible or "—"}'
                                   if change_type == '部门转移' else '')
                                + (f'；实际使用人：{old_user or "—"} → {new_user or "—"}'
                                   if change_type == '部门转移' else '')
                                + ('' if ok2 else '（资产同步未完成）')),
                    )
                return redirect('change')
    return redirect('change')


def _validate_change(change_type, new_value):
    """校验一条资产变更能否真正同步到台账。返回 (ok, error_msg)。

    - change_type 必须在系统支持的变更类型内（部门转移/状态变更）。
    - 部门转移：目标部门必须已存在于组织架构，禁止自动新建错误部门。
    - 状态变更：目标状态必须为资产状态枚举中的合法值。
    """
    new_value = (new_value or '').strip()
    valid_types = [c[0] for c in AssetChange.CHANGE_TYPES]
    if change_type not in valid_types:
        return False, f'变更类型「{change_type or "空"}」无效，仅支持：{"、".join(valid_types)}'
    if change_type == '部门转移':
        if not new_value:
            return False, '未填写「变更后」的目标部门。'
        if not Department.objects.filter(name=new_value).exists():
            return False, f'目标部门「{new_value}」在组织架构中不存在，请先在组织架构中创建或核对部门名称。'
    elif change_type == '状态变更':
        valid = [c[0] for c in Asset.STATUS_CHOICES]
        if new_value not in valid:
            return False, f'状态「{new_value or "空"}」无效，仅支持：{"、".join(valid)}'
    return True, None


def _apply_change_sync(asset, change_type, new_value, new_responsible=None, new_user=None):
    """按变更类型把变更应用到资产台账（应在 _validate_change 通过后调用）。返回 (ok, msg)。

    部门转移时可连带同步新责任人 / 新实际使用人（传 None 或空串表示不变）。
    """
    from django.db import transaction
    with transaction.atomic():
        if change_type == '部门转移':
            dept = Department.objects.get(name=new_value)
            asset.department = dept
            update_fields = ['department']
            if new_responsible:
                asset.responsible = new_responsible
                update_fields.append('responsible')
            if new_user:
                asset.user = new_user
                update_fields.append('user')
            asset.save(update_fields=update_fields)
        elif change_type == '状态变更':
            asset.status = new_value
            asset.save(update_fields=['status'])
        else:
            return False, '未知变更类型，未同步'
    return True, None


@perm_required('manage_change')
def change_update(request, pk):
    ch = get_object_or_404(AssetChange, pk=pk)
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        ch.change_type = request.POST.get('change_type', ch.change_type)
        ch.old_value = request.POST.get('old_value', '').strip()
        ch.new_value = request.POST.get('new_value', '').strip()
        ch.old_responsible = request.POST.get('old_responsible', '').strip()
        ch.old_user = request.POST.get('old_user', '').strip()
        ch.new_responsible = request.POST.get('new_responsible', '').strip()
        ch.new_user = request.POST.get('new_user', '').strip()
        ch.changed_by = request.POST.get('changed_by', '').strip()
        ch.note = request.POST.get('note', '').strip()
        missing = []
        if not ch.change_type:
            missing.append('变更类型')
        if not reason:
            missing.append('变更原因')
        if not ch.old_value:
            missing.append('变更前')
        if not ch.new_value:
            missing.append('变更后')
        if not ch.changed_by:
            missing.append('经办人')
        if missing:
            messages.error(request, '请填写必填项：' + '、'.join(missing))
            return render(request, 'change_form.html', {'ch': ch, 'page_title': '编辑变更', 'active': 'change'})
        ch.reason = reason
        # 先校验可同步性，失败则不保存
        ok, msg = _validate_change(ch.change_type, ch.new_value)
        if not ok:
            messages.error(request, msg)
            return render(request, 'change_form.html', {'ch': ch, 'page_title': '编辑变更', 'active': 'change'})
        from django.db import transaction
        with transaction.atomic():
            ch.save()
            ok2, msg2 = _apply_change_sync(
                ch.asset, ch.change_type, ch.new_value,
                new_responsible=ch.new_responsible if ch.change_type == '部门转移' else None,
                new_user=ch.new_user if ch.change_type == '部门转移' else None,
            )
        if ok2:
            messages.success(request, '变更记录已更新，并同步到资产库。')
        else:
            messages.warning(request, '变更记录已更新，但资产同步未完成：' + (msg2 or ''))
        oplog.log(request, 'change', 'update', target=_asset_label(ch.asset),
                  detail=(f'修改变更记录 → {ch.change_type}：{ch.old_value} → {ch.new_value}；'
                          f'原因：{ch.reason}'
                          + ('' if ok2 else '（资产同步未完成）')))
        return redirect('change')
    context = {'ch': ch, 'page_title': '编辑变更', 'active': 'change'}
    return render(request, 'change_form.html', context)


@perm_required('manage_change')
def change_delete(request, pk):
    ch = get_object_or_404(AssetChange, pk=pk)
    if request.method == 'POST':
        target = _asset_label(ch.asset)
        detail = f'删除变更记录（{ch.change_type}：{ch.old_value} → {ch.new_value}）'
        ch.delete()
        oplog.log(request, 'change', 'delete', target=target, detail=detail)
        messages.success(request, '变更记录已删除。')
    return redirect('change')

