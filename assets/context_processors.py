from django.contrib.messages import get_messages


def messages_json(request):
    """把 Django 消息整理为列表，供模板用 json_script 安全输出（避免直接拼进 script）。"""
    return {
        'messages_json': [
            {'level': m.level_tag, 'message': str(m)}
            for m in get_messages(request)
        ]
    }
