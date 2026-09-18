"""资产附件：上传 / 删除 / 受控下载。"""

import os

from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import redirect, get_object_or_404

from .. import oplog
from ..models import Asset, AssetAttachment
from ..permissions import perm_required
from .common import _asset_label

@perm_required('manage_assets')
def attachment_upload(request, pk):
    """为资产上传附件（支持一次多选）。"""
    asset = get_object_or_404(Asset, pk=pk)
    if request.method == 'POST':
        files = request.FILES.getlist('files')
        if not files:
            messages.error(request, '请先选择要上传的文件。')
            return redirect('asset_update', pk=pk)

        allowed_text = '、'.join(AssetAttachment.ALLOWED_EXT)
        max_mb = AssetAttachment.MAX_SIZE // (1024 * 1024)
        ok, errors = 0, []
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in AssetAttachment.ALLOWED_EXT:
                errors.append(f'「{f.name}」格式不允许（支持：{allowed_text}）')
                continue
            if f.size > AssetAttachment.MAX_SIZE:
                errors.append(f'「{f.name}」超过 {max_mb}MB 上限')
                continue
            att = AssetAttachment.objects.create(
                asset=asset, file=f, name=f.name[:200], size=f.size,
                uploaded_by=(request.user.first_name or request.user.username),
            )
            oplog.log(request, 'attachment', 'create', target=_asset_label(asset),
                      detail=f'上传附件：{att.name}（{att.size_h}）')
            ok += 1

        if ok:
            messages.success(request, f'已上传 {ok} 个附件。')
        for e in errors:
            messages.error(request, e)
    return redirect('asset_update', pk=pk)


@perm_required('manage_assets')
def attachment_delete(request, pk):
    att = get_object_or_404(AssetAttachment, pk=pk)
    asset_pk = att.asset_id
    if request.method == 'POST':
        name = att.name
        asset_label = _asset_label(att.asset)
        try:
            att.file.delete(save=False)  # 一并删除物理文件
        except Exception:  # noqa: BLE001 — 文件已丢失也要能删记录
            pass
        att.delete()
        oplog.log(request, 'attachment', 'delete', target=asset_label, detail=f'删除附件：{name}')
        messages.success(request, f'附件「{name}」已删除。')
    return redirect('asset_update', pk=asset_pk)


@perm_required('view_assets')
def attachment_download(request, pk):
    """附件下载：走登录 + 权限校验，不直接暴露媒体目录。"""
    att = get_object_or_404(AssetAttachment, pk=pk)
    try:
        path = att.file.path
    except Exception:  # noqa: BLE001
        raise Http404('附件路径无效')
    if not os.path.exists(path):
        raise Http404('附件文件已丢失')
    return FileResponse(
        open(path, 'rb'), as_attachment=True,
        filename=att.name or os.path.basename(path),
    )

