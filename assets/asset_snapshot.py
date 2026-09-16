"""资产信息快照 —— 把资产关键字段压成一段可直接放进二维码的短文本。

为什么要"快照"而不是"扫码去查库"：

资产标签贴到设备上以后，扫码的人不一定有系统账号（例如第三方运维、
检查人员，或者就是不想登录的同事）。所以生成二维码时把关键字段做成
**快照**，信息本身跟着二维码走；扫码落地页只读这一份快照，
既不要求登录，也不访问数据库，改参数也无法枚举出其它资产。

快照是"生成时"的：资产后来发生变更，不会回溯修改已经打印出去的标签。
这是刻意为之 —— 标签上的信息与打印那一刻的台账一致，便于盘点核对；
但也意味着**资产信息变更后需要重新打印标签**。

快照时间只精确到**日期**（字段 ``snapshot_date``）：盘点只需知道"哪天的台账"，
而且这样同一个资产在一天内生成的二维码内容完全一致 —— 内容不变，
二维码图片就能按内容复用（见 ``views.asset_qr`` 的内容寻址缓存），
不用每次翻页都重新算一遍二维码。

编码：定长字段按 :data:`FIELDS` 顺序用 ``|`` 连接，整体做 base64url。
字段里的 ``|`` 会被替换成全角斜杠，避免破坏分隔。
为了控制二维码密度，字段有长度上限，并按三档逐步收紧，
保证最终文本不超过 :data:`RAW_LIMIT` 字节。
"""
import base64

from django.utils import timezone

SEP = '|'

#: 快照原始文本的字节上限。约 190 字节 → base64 后 256 字符，
#: 连同短域名组成约 280 字符的链接，二维码版本约 13 级（69×69），
#: 在 26mm 的标签上每个模块约 0.38mm，手机近距离扫码清晰可读。
RAW_LIMIT = 190

#: 字段顺序 —— 解码端依赖这个顺序，**不要随意调整**。
FIELDS = (
    'asset_id', 'name', 'category', 'status', 'specification',
    'responsible', 'user', 'department', 'location',
    'price', 'purchase_date', 'serial', 'snapshot_date',
)

#: 字段中文名（落地页展示用）。
LABELS = {
    'asset_id': '资产编号',
    'name': '资产名称',
    'category': '资产类别',
    'status': '使用状态',
    'specification': '规格',
    'responsible': '责任人',
    'user': '实际使用人',
    'department': '所属部门',
    'location': '存放位置',
    'price': '资产价值',
    'purchase_date': '购置日期',
    'serial': '序列号',
    'snapshot_date': '快照日期',
}

#: 落地页字段展示顺序（资产编号/状态已在页头展示，不重复）。
CARD_FIELDS = (
    'category', 'specification', 'department', 'responsible', 'user',
    'location', 'price', 'purchase_date', 'serial',
)

# 长度上限三档：先宽松，超长则收紧，最后只保留最关键的几个字段。
# 未列出的字段不裁剪（资产编号、金额、日期本身就很短）。
_LIMIT_TIERS = (
    {
        'name': 24, 'category': 12, 'status': 10, 'specification': 20,
        'responsible': 12, 'user': 12, 'department': 16, 'location': 18,
        'serial': 16,
    },
    {
        'name': 16, 'category': 8, 'status': 10, 'specification': 10,
        'responsible': 8, 'user': 8, 'department': 12, 'location': 12,
        'serial': 10,
    },
    {
        'name': 12, 'category': 6, 'status': 10, 'specification': 0,
        'responsible': 6, 'user': 6, 'department': 10, 'location': 8,
        'serial': 0,
    },
)

#: 状态 → 落地页配色（与系统内状态语义保持一致）。
STATUS_TONES = {
    '在用': 'ok',
    '库存': 'muted',
    '借出': 'warn',
    '维修': 'info',
    '报废': 'bad',
}


def _clean(text, limit=None):
    """清理单个字段：吃掉换行、替换分隔符、必要时截断。"""
    text = str(text or '').replace(SEP, '／')
    text = ' '.join(text.split())
    if limit is not None and len(text) > limit:
        text = text[:limit]
    return text


def _money(value):
    try:
        return f'{value:.2f}'
    except (TypeError, ValueError):
        return ''


def values_of(asset, at=None):
    """把资产对象摊平成「字段 → 文本」，可脱离数据库单独测试。"""
    at = at or timezone.localtime()
    return {
        'asset_id': asset.asset_id,
        'name': asset.name,
        'category': asset.category,
        'status': asset.status,
        'specification': asset.specification,
        'responsible': asset.responsible,
        'user': asset.user,
        'department': asset.department.name if asset.department_id else '',
        'location': asset.location,
        'price': _money(asset.price),
        'purchase_date': asset.purchase_date.isoformat() if asset.purchase_date else '',
        'serial': asset.serial,
        'snapshot_date': at.strftime('%Y-%m-%d'),
    }


def raw_text(asset, at=None):
    """生成快照明文（``|`` 分隔）。超长时按档位收紧字段长度。"""
    values = values_of(asset, at)
    for limits in _LIMIT_TIERS:
        raw = SEP.join(_clean(values[f], limits.get(f)) for f in FIELDS)
        if len(raw.encode('utf-8')) <= RAW_LIMIT:
            return raw
    # 兜底：字段全中文且特别长时按字节硬截断，解码端允许字段缺失。
    raw = SEP.join(_clean(values[f], limits.get(f)) for f in FIELDS)
    while len(raw.encode('utf-8')) > RAW_LIMIT:
        raw = raw[:-1]
    return raw


def encode(asset, at=None):
    """返回放进二维码的短文本（base64url，可安全拼在 URL 查询串里）。"""
    raw = raw_text(asset, at)
    return base64.urlsafe_b64encode(raw.encode('utf-8')).decode('ascii').rstrip('=')


def decode(token):
    """把二维码里的快照还原成 dict；内容无效时返回 ``None``。

    不做任何数据库查询 —— 页面能显示什么，完全取决于二维码里带什么。
    """
    token = (token or '').strip()
    if not token:
        return None
    pad = '=' * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + pad).decode('utf-8')
    except Exception:
        return None
    parts = raw.split(SEP)
    # 至少要能看出是哪台资产，否则视为无效二维码。
    if len(parts) < 2 or not parts[0].strip():
        return None
    return {f: (parts[i] if i < len(parts) else '') for i, f in enumerate(FIELDS)}


def card_payload(base, asset, at=None):
    """拼出二维码真正要编码的链接：``<base>/a/?d=<快照>``。

    ``base`` 是扫码落地页的绝对地址（由调用方按当前访问域名生成，
    所以标签跟着当前访问方式走，不受写死域名影响）。
    """
    base = base.split('?')[0]
    return base + '?' + 'd=' + encode(asset, at)


def status_tone(status):
    """状态 → 配色关键字，未知状态按普通处理。"""
    return STATUS_TONES.get((status or '').strip(), 'muted')
