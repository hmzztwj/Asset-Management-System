import json

from django.contrib.messages import get_messages


def messages_json(request):
    """把 Django 消息转为 JSON，供前端 Toast 提示使用。"""
    msgs = [
        {'level': m.level_tag, 'message': str(m)}
        for m in get_messages(request)
    ]
    return {'messages_json': json.dumps(msgs, ensure_ascii=False)}
