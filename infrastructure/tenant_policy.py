"""Single tenant policy gate for AI runtime and live-data activation."""
from __future__ import annotations

from dataclasses import dataclass

from infrastructure.tenant_admin_store import get_tenant_admin_store


class TenantPolicyError(PermissionError):
    """An operation conflicts with the tenant's configured data policy."""


@dataclass(frozen=True)
class TenantPolicy:
    tenant_id: str
    mode: str
    allowed_providers: frozenset[str]
    cloud_egress: str

    @property
    def permits_cloud_egress(self) -> bool:
        return self.cloud_egress != "blocked"

    def require_provider(self, provider: str) -> None:
        if provider not in self.allowed_providers:
            raise TenantPolicyError(
                f"{provider.title()} is blocked by the tenant's {self.mode} AI deployment policy"
            )

    def require_legacy_connector(self, provider: str) -> None:
        if not self.permits_cloud_egress:
            raise TenantPolicyError(
                f"{provider} cannot be activated for a {self.mode} tenant. Use the governed local/private connector path."
            )

    def require_external_connection(self, provider: str) -> None:
        """Gate a tenant-configured live provider against the data boundary."""
        if not self.permits_cloud_egress:
            raise TenantPolicyError(
                f"{provider} cannot be connected for a {self.mode} tenant because cloud egress is blocked"
            )


def get_tenant_policy(tenant_id: str) -> TenantPolicy:
    profile = get_tenant_admin_store().operating_profile(tenant_id)
    deployment = profile["deployment_policy"]
    return TenantPolicy(
        tenant_id=tenant_id,
        mode=str(profile["deployment_mode"]),
        allowed_providers=frozenset(deployment["allowed_providers"]),
        cloud_egress=str(deployment["cloud_egress"]),
    )
