import uuid

from app.services.security_service import SecurityService
from app.services.rbac_service import RBACService


def _unique(name: str) -> str:
    return f"{name}_{uuid.uuid4().hex[:6]}"


def test_user_permissions_basic_access():
    security = SecurityService()
    rbac = RBACService()

    username = _unique("user")
    security.create_user_admin(username=username, password="Abcd1234", role="user")
    user = rbac.get_user(username)

    doc_id = _unique("doc")
    rbac.set_document_permissions(
        document_id=doc_id,
        org_id=user["org_id"],
        owner_username=username,
        access_level="private",
        allowed_users=[username],
    )

    assert rbac.can_access_document(user, doc_id) is True


def test_user_cannot_access_other_org():
    security = SecurityService()
    rbac = RBACService()

    username = _unique("user")
    security.create_user_admin(username=username, password="Abcd1234", role="user", org_id="default")
    user = rbac.get_user(username)

    doc_id = _unique("doc")
    rbac.set_document_permissions(
        document_id=doc_id,
        org_id="other_org",
        owner_username="someone",
        access_level="org",
    )

    assert rbac.can_access_document(user, doc_id, {"org_id": "other_org"}) is False
