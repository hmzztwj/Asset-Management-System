from django.contrib.messages import get_messages

# 常见移动端 UA 特征（覆盖 iOS / Android / 鸿蒙及主流国产浏览器）
_MOBILE_UA_MARKS = (
    'Mobile', 'Android', 'iPhone', 'iPad', 'iPod', 'HarmonyOS', 'HMOS',
    'Windows Phone', 'OPPO', 'vivo', 'HUAWEI', 'MIUI', 'MiniProgramApp',
)


def device_type(request):
    """根据 User-Agent 识别访问设备，模板可据此切换移动端/桌面端布局。"""
    ua = request.META.get('HTTP_USER_AGENT', '') or ''
    return {'is_mobile': any(mark in ua for mark in _MOBILE_UA_MARKS)}


def messages_json(request):
    """把 Django 消息整理为列表，供模板用 json_script 安全输出（避免直接拼进 script）。"""
    return {
        'messages_json': [
            {'level': m.level_tag, 'message': str(m)}
            for m in get_messages(request)
        ]
    }
