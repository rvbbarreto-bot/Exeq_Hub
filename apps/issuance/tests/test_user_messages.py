"""Mensagens amigáveis NFS-e."""

from __future__ import annotations

import pytest

from apps.issuance.models import NfIssue
from apps.issuance.user_messages import (
    enrich_issue_events,
    nf_actor_label,
    nf_status_label,
    rejection_display,
)


def test_nf_status_label_maps_internal_codes():
    assert nf_status_label("pending_tax") == "Tributação"
    assert nf_status_label("draft") == "Rascunho"
    assert nf_status_label("") == "—"


def test_nf_actor_label_maps_technical_actors():
    assert nf_actor_label("worker") == "Processamento automático"
    assert nf_actor_label("api") == "Emissão via sistema"
    assert nf_actor_label("ricardo@exeq.com.br") == "Usuário (ricardo@exeq.com.br)"


@pytest.mark.django_db
def test_rejection_display_cert_not_usable():
    issue = NfIssue(rejection_code="CERT_NOT_USABLE", status=NfIssue.Status.FAILED)
    out = rejection_display(issue)
    assert out is not None
    assert "Certificado" in out["title"]
    assert "Certificados" in out["hint"]
    assert out["code"] == "CERT_NOT_USABLE"


@pytest.mark.django_db
def test_rejection_display_sefin_e0207_with_message():
    issue = NfIssue(
        rejection_code="E0207",
        status=NfIssue.Status.REJECTED,
        focus_status_raw={
            "erros": [{"codigo": "E0207", "mensagem": "CPF do tomador invalido na RFB"}],
        },
    )
    out = rejection_display(issue)
    assert out is not None
    assert "Tomador" in out["title"]
    assert "CPF do tomador" in out["message"]
    assert out["code"] == "E0207"


@pytest.mark.django_db
def test_enrich_issue_events_labels():
    class Ev:
        occurred_at = None
        from_status = "draft"
        to_status = "pending_tax"
        actor = "api"

    rows = enrich_issue_events([Ev()])
    assert rows[0]["from_label"] == "Rascunho"
    assert rows[0]["to_label"] == "Tributação"
    assert rows[0]["actor_label"] == "Emissão via sistema"
