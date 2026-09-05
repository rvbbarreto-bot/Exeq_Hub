"""Formulários Admin — Tenant."""

from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.models import Tenant
from apps.accounts.tenant_emission import (
    apply_emission_flags,
    emission_flags_from_settings,
)


class TenantAdminForm(forms.ModelForm):
    emit_nfse = forms.BooleanField(
        label="Emissão Nota Fiscal de Serviço (NFS-e)",
        required=False,
        initial=True,
        help_text="Habilita NFS-e (serviço) no Hub e na API deste escritório.",
    )
    emit_nfe = forms.BooleanField(
        label="Emissão Nota Fiscal de produto (NF-e)",
        required=False,
        initial=False,
        help_text=(
            "Habilita NF-e modelo 55 no tenant. Requer também NFE_ENABLED=true "
            "no ambiente (servidor)."
        ),
    )
    emit_nfce = forms.BooleanField(
        label="Emissão cupom fiscal PDV (NFC-e)",
        required=False,
        initial=False,
        help_text=(
            "Habilita NFC-e modelo 65 no tenant. Requer NFCE_ENABLED=true no servidor."
        ),
    )

    class Meta:
        model = Tenant
        fields = (
            "slug",
            "legal_name",
            "document",
            "status",
            "focus_layout",
            "settings",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cfg = self.instance.settings if self.instance and self.instance.pk else {}
        nfse, nfe, nfce = emission_flags_from_settings(cfg)
        self.fields["emit_nfse"].initial = nfse
        self.fields["emit_nfe"].initial = nfe
        self.fields["emit_nfce"].initial = nfce
        self.fields["settings"].help_text = (
            "Configurações avançadas (JSON). Flags nfse_enabled, nfe_enabled e "
            "nfce_enabled são definidas pelos checkboxes acima."
        )

    def clean(self):
        cleaned = super().clean()
        nfse = bool(cleaned.get("emit_nfse"))
        nfe = bool(cleaned.get("emit_nfe"))
        nfce = bool(cleaned.get("emit_nfce"))
        if not nfse and not nfe and not nfce:
            raise ValidationError(
                "Selecione pelo menos um tipo de emissão: NFS-e, NF-e e/ou NFC-e."
            )
        cleaned["emit_nfse"] = nfse
        cleaned["emit_nfe"] = nfe
        cleaned["emit_nfce"] = nfce
        return cleaned

    def save(self, commit=True):
        tenant = super().save(commit=False)
        tenant.settings = apply_emission_flags(
            tenant.settings,
            nfse=self.cleaned_data["emit_nfse"],
            nfe=self.cleaned_data["emit_nfe"],
            nfce=self.cleaned_data["emit_nfce"],
        )
        if commit:
            tenant.save()
        return tenant
