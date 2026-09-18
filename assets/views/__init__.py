"""视图层（按业务域拆分自原单文件 views.py）。urls.py 仍以 views.<名> 引用。"""

from .auth import (  # noqa: F401
    login_view, logout_view, password_change,
)
from .dashboard import (  # noqa: F401
    dashboard,
)
from .library import (  # noqa: F401
    library, assets_bulk_delete, asset_create, asset_update, asset_delete, asset_import, asset_import_template,
)
from .org import (  # noqa: F401
    org, department_form, department_delete,
)
from .requisition import (  # noqa: F401
    requisition, requisition_export, requisition_create, requisition_return, requisition_edit, requisition_delete,
)
from .change import (  # noqa: F401
    change, change_export, change_create, change_update, change_delete,
)
from .account import (  # noqa: F401
    user_list, user_create, user_update, user_delete, role_list, role_create, role_update, role_delete,
)
from .qr import (  # noqa: F401
    asset_qr, asset_card, asset_labels,
)
from .attachments import (  # noqa: F401
    attachment_upload, attachment_delete, attachment_download,
)
from .oplog import (  # noqa: F401
    oplog_list,
)

__all__ = [
    'login_view',
    'logout_view',
    'password_change',
    'dashboard',
    'library',
    'assets_bulk_delete',
    'asset_create',
    'asset_update',
    'asset_delete',
    'asset_import',
    'asset_import_template',
    'org',
    'department_form',
    'department_delete',
    'requisition',
    'requisition_export',
    'requisition_create',
    'requisition_return',
    'requisition_edit',
    'requisition_delete',
    'change',
    'change_export',
    'change_create',
    'change_update',
    'change_delete',
    'user_list',
    'user_create',
    'user_update',
    'user_delete',
    'role_list',
    'role_create',
    'role_update',
    'role_delete',
    'asset_qr',
    'asset_card',
    'asset_labels',
    'attachment_upload',
    'attachment_delete',
    'attachment_download',
    'oplog_list',
]
