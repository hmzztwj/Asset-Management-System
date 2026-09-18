"""资产二维码 / 标签打印 / 免登录扫码信息卡。"""

import hashlib
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.cache import get_conditional_response
from django.views.decorators.http import require_GET

from .. import asset_snapshot as snapshot
from ..models import Asset
from ..permissions import perm_required
from ..qr import qr_svg
from .common import _filtered_assets

_LOCAL_HOSTS = ('127.0.0.1', 'localhost', '[::1]', '0.0.0.0')


QR_CACHE_SECONDS = 24 * 3600


def _cached_qr_svg(payload):
    """按内容缓存二维码图片。

    二维码内容里带了资产快照，所以"内容相同"就等于"图相同"——
    直接用内容做缓存键：资产没变就命中缓存，资产一改内容就变、自然重算，
    不需要任何失效逻辑。生成一张要 ~30ms，标签页动辄上百张，这层缓存很关键。
    """
    key = 'assetqr:' + hashlib.md5(payload.encode('utf-8')).hexdigest()
    svg = cache.get(key)
    if svg is None:
        svg = qr_svg(payload)
        cache.set(key, svg, QR_CACHE_SECONDS)
    return svg


def _card_base_url(request):
    """二维码里要写哪个地址（不含路径）。

    优先用配置里的固定地址（``ASSETS_PUBLIC_BASE_URL``），没配就退回
    「当前访问地址」——后者在本机用 127.0.0.1 访问时会把 127.0.0.1 打进
    标签，手机扫了打不开，所以页面会给出提示。
    """
    fixed = (getattr(settings, 'PUBLIC_BASE_URL', '') or '').strip().rstrip('/')
    if fixed:
        return fixed
    return request.build_absolute_uri('/').rstrip('/')


def _is_local_base(url):
    """二维码地址是不是只有本机才能打开。"""
    host = (urlsplit(url or '').hostname or '').lower()
    return host in _LOCAL_HOSTS or host.startswith('127.')


@perm_required('view_assets')
def asset_qr(request, pk):
    """返回单个资产的二维码图片（SVG）。

    默认把「资产信息快照」编码进二维码：扫码后直接看到一个只读信息卡
    （``asset_card``），**不需要登录，也不会落到资产库列表页**。
    信息跟着二维码走，所以标签贴出去之后，没账号的人也能看清这是什么资产。

    二维码里写哪个地址由 ``_card_base_url`` 决定：配了
    ``ASSETS_PUBLIC_BASE_URL`` 就固定用它，否则跟着当前访问地址走。

    二维码在本机离线生成，不依赖任何外部服务。响应带 ETag 且要求浏览器
    每次校验：资产一改，扫码内容立刻变新，不会把旧快照打进标签。
    """
    asset = get_object_or_404(Asset.objects.select_related('department'), pk=pk)
    base = _card_base_url(request) + reverse('asset_card')
    payload = snapshot.card_payload(base, asset)

    response = HttpResponse(_cached_qr_svg(payload), content_type='image/svg+xml')
    response['ETag'] = '"%s"' % hashlib.md5(payload.encode('utf-8')).hexdigest()
    response['Cache-Control'] = 'private, no-cache, max-age=0'
    return get_conditional_response(request, etag=response['ETag'], response=response) or response


@require_GET
def asset_card(request):
    """扫码落地页：直接显示二维码里携带的资产信息快照。

    * **免登录**：扫码的人不需要系统账号；
    * **只读**：没有任何编辑/跳转入口，只有一个返回说明；
    * **不查库**：页面内容全部来自 ``?d=`` 参数，改参数也枚举不出别的资产。

    参数缺失或损坏时给出可读的提示页，而不是报错栈。
    """
    data = snapshot.decode(request.GET.get('d', ''))
    fields = []
    if data:
        for key in snapshot.CARD_FIELDS:
            value = (data.get(key) or '').strip()
            if not value:
                continue
            if key == 'price':
                # 台账里 0 元多半是"未估值"，显示 ¥0.00 反而像出错，直接略过。
                if value in ('0.00', '0'):
                    continue
                value = f'¥ {value}'
            fields.append({'key': key, 'label': snapshot.LABELS[key], 'value': value})

    context = {
        'a': data,
        'fields': fields,
        'tone': snapshot.status_tone(data['status']) if data else 'muted',
    }
    response = render(request, 'asset_card.html', context)
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@perm_required('view_assets')
def asset_labels(request):
    """标签打印页：把所选（或当前筛选）资产排成便于裁剪张贴的标签。

    取值优先级：
    1. ``?ids=1,2,3`` —— 资产库勾选后点「打印标签」（最常用）；
    2. 否则复用资产库的筛选参数（状态/类别/部门/关键字），最多 200 张。
    """
    ids_raw = (request.GET.get('ids') or '').strip()
    if ids_raw:
        ids = [int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
        assets = list(
            Asset.objects.select_related('department').filter(pk__in=ids).order_by('asset_id')
        )
    else:
        qs, _ = _filtered_assets(request)
        assets = list(qs.order_by('asset_id')[:200])

    # 版式：grid = A4 三列 60×40mm（默认）；tag = 60×40mm 标签纸单张
    layout = request.GET.get('layout') or 'grid'
    if layout not in ('grid', 'tag'):
        layout = 'grid'
    # 版式切换链接：保留 ids 参数
    keep_ids = f'ids={ids_raw}&' if ids_raw else ''
    _url = lambda v: ('?' + keep_ids + 'layout=' + v) if keep_ids else ('?layout=' + v)

    # 二维码里会写入的地址：让用户在打印前就能看见、能核对
    qr_base = _card_base_url(request)
    qr_base_fixed = bool((getattr(settings, 'PUBLIC_BASE_URL', '') or '').strip())

    context = {
        'assets': assets,
        'layout': layout,
        'qr_base': qr_base,
        'qr_base_local': _is_local_base(qr_base),
        'qr_base_fixed': qr_base_fixed,
        'url_grid': _url('grid'),
        'url_tag': _url('tag'),
        'page_title': '资产标签打印',
        'active': 'library',
    }
    return render(request, 'asset_labels.html', context)

