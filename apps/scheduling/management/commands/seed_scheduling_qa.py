"""Seed idempotente do EXEQ Agendador para QA / integração local."""

from __future__ import annotations

from datetime import time
from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Tenant, TenantMembership, User
from apps.accounts.services import ensure_system_roles
from apps.master_data.models import Customer, Provider, TaxRegime
from apps.scheduling.models import (
    BusinessHours,
    CommissionRule,
    Professional,
    ProfessionalService,
    Service,
)

TENANT_SLUG = "agendador-qa"
TENANT_DOCUMENT = "33445566000177"
USER_EMAIL = "agenda.qa@exeq.local"
USER_PASSWORD = "AgendaQa123!"

# UUIDs fixos para roteiros de QA reproduzíveis
PROVIDER_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-111111111111")
CUSTOMER_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-222222222222")
CUSTOMER_RESTRICTED_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-222222222223")
PROFESSIONAL_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-333333333333")
SERVICE_CORTE_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-444444444444")
SERVICE_BARBA_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-444444444445")
COMMISSION_RULE_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-555555555555")


class Command(BaseCommand):
    help = (
        "Cria tenant/usuário/cadastros mínimos do Agendador para testes QA "
        f"(tenant={TENANT_SLUG}, user={USER_EMAIL})."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-hours",
            action="store_true",
            help="Recria horários comerciais do profissional seed.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        roles = {r.code: r for r in ensure_system_roles()}
        tenant, t_created = Tenant.objects.get_or_create(
            slug=TENANT_SLUG,
            defaults={
                "legal_name": "Barbearia QA Agendador LTDA",
                "document": TENANT_DOCUMENT,
                "status": Tenant.Status.ACTIVE,
                "settings": {},
            },
        )
        if not t_created and tenant.document != TENANT_DOCUMENT:
            # slug already taken with another CNPJ — keep existing
            pass

        user, u_created = User.objects.get_or_create(
            email=USER_EMAIL,
            defaults={
                "name": "QA Agendador",
                "is_active": True,
                "is_staff": True,
            },
        )
        user.name = "QA Agendador"
        user.is_active = True
        user.is_staff = True
        user.set_password(USER_PASSWORD)
        user.save()

        membership, _ = TenantMembership.objects.get_or_create(
            tenant=tenant,
            user=user,
            defaults={"role": roles["tenant_admin"], "is_active": True},
        )
        if membership.role_id != roles["tenant_admin"].id:
            membership.role = roles["tenant_admin"]
            membership.is_active = True
            membership.save(update_fields=["role", "is_active", "updated_at"])

        provider, _ = Provider.objects.update_or_create(
            id=PROVIDER_ID,
            defaults={
                "tenant": tenant,
                "document": "11222333000181",
                "legal_name": "Prestador QA Agenda",
                "trade_name": "Barbearia QA",
                "tax_regime": TaxRegime.SIMPLES,
                "is_active": True,
            },
        )

        customer, _ = Customer.objects.update_or_create(
            id=CUSTOMER_ID,
            defaults={
                "tenant": tenant,
                "document": "52998224725",
                "document_type": Customer.DocumentType.CPF,
                "name": "Cliente QA WhatsApp",
                "whatsapp": "+5511999001122",
                "email": "cliente.qa@exeq.local",
                "is_active": True,
            },
        )
        Customer.objects.update_or_create(
            id=CUSTOMER_RESTRICTED_ID,
            defaults={
                "tenant": tenant,
                "document": "39053344705",
                "document_type": Customer.DocumentType.CPF,
                "name": "Cliente QA Restrito",
                "whatsapp": "",
                "is_active": True,
            },
        )

        professional, _ = Professional.objects.update_or_create(
            id=PROFESSIONAL_ID,
            defaults={
                "tenant": tenant,
                "provider": provider,
                "user": user,
                "name": "Barbeiro QA João",
                "timezone": "America/Sao_Paulo",
                "is_active": True,
            },
        )

        corte, _ = Service.objects.update_or_create(
            id=SERVICE_CORTE_ID,
            defaults={
                "tenant": tenant,
                "name": "Corte masculino",
                "duration_minutes": 30,
                "price_cents": 5000,
                "buffer_before_minutes": 0,
                "buffer_after_minutes": 5,
                "is_active": True,
            },
        )
        barba, _ = Service.objects.update_or_create(
            id=SERVICE_BARBA_ID,
            defaults={
                "tenant": tenant,
                "name": "Barba",
                "duration_minutes": 20,
                "price_cents": 3500,
                "buffer_before_minutes": 0,
                "buffer_after_minutes": 0,
                "is_active": True,
            },
        )

        for svc in (corte, barba):
            ProfessionalService.objects.get_or_create(
                tenant=tenant,
                professional=professional,
                service=svc,
            )

        if options["reset_hours"]:
            BusinessHours.objects.filter(
                tenant=tenant, professional=professional
            ).delete()

        if not BusinessHours.objects.filter(
            tenant=tenant, professional=professional
        ).exists():
            for dow in (1, 2, 3, 4, 5):  # seg–sex (DOW: 0=domingo)
                BusinessHours.objects.create(
                    tenant=tenant,
                    professional=professional,
                    weekday=dow,
                    starts_at=time(9, 0),
                    ends_at=time(18, 0),
                )

        CommissionRule.objects.update_or_create(
            id=COMMISSION_RULE_ID,
            defaults={
                "tenant": tenant,
                "professional": None,
                "service": None,
                "rule_kind": CommissionRule.RuleKind.PERCENT,
                "percent_basis_points": 4000,
                "fixed_cents": None,
                "priority": 1,
                "is_active": True,
            },
        )

        self.stdout.write(self.style.SUCCESS("Seed Agendador QA OK"))
        self.stdout.write(f"  tenant_slug: {tenant.slug}")
        self.stdout.write(f"  email:       {USER_EMAIL}")
        self.stdout.write(f"  password:    {USER_PASSWORD}")
        self.stdout.write(f"  provider:    {provider.id}")
        self.stdout.write(f"  customer:    {customer.id}")
        self.stdout.write(f"  professional:{professional.id}")
        self.stdout.write(f"  service_corte:{corte.id}")
        self.stdout.write(f"  service_barba:{barba.id}")
        self.stdout.write(
            "  login API: POST /api/v1/auth/login "
            f'{{"tenant_slug":"{TENANT_SLUG}","email":"{USER_EMAIL}","password":"…"}}'
        )
