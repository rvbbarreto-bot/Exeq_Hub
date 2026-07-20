from django.db import models

from shared.models import TimeStampedModel


class TenantOwnedModel(TimeStampedModel):
    tenant = models.ForeignKey(
        "accounts.Tenant",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="Tenant",
    )

    class Meta:
        abstract = True
