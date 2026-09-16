import builtins

from django import template

from ..permissions import user_has_perm

register = template.Library()


@register.filter
def has_perm(user, perm):
    """判断用户是否拥有某权限，模板用法：{{ user|has_perm:'manage_assets' }}"""
    return user_has_perm(user, perm)


@register.filter
def split(value, sep=','):
    """Split a string into a list by the given separator."""
    if value is None:
        return []
    return str(value).split(sep)


@register.filter(name='getattr')
def getattr_filter(value, arg):
    """返回对象的属性值（如 {{ obj|getattr:'field' }}）。

    注意：函数体内必须用 ``builtins.getattr``——如果直接写 ``getattr(value, arg)``
    会递归调用本过滤器自身，抛 RecursionError 被 except 吞掉，永远返回空串
    （曾导致角色编辑页勾选框全部不回显，看起来像权限没保存）。
    """
    try:
        return builtins.getattr(value, arg)
    except Exception:
        return ''
