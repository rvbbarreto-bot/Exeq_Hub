from django.urls import path

from apps.nfce.views import (
    NfceCheckoutView,
    NfceConfigView,
    NfceGateView,
    NfceInvoiceViewSet,
    NfcePolicyPreviewView,
)

invoice_list = NfceInvoiceViewSet.as_view({"get": "list", "post": "create"})
invoice_detail = NfceInvoiceViewSet.as_view({"get": "retrieve"})
invoice_items = NfceInvoiceViewSet.as_view({"put": "items"})
invoice_validate = NfceInvoiceViewSet.as_view({"post": "validate"})
invoice_emit = NfceInvoiceViewSet.as_view({"post": "emit"})
invoice_cancel = NfceInvoiceViewSet.as_view({"post": "cancel"})
invoice_events = NfceInvoiceViewSet.as_view({"get": "events"})
invoice_xml = NfceInvoiceViewSet.as_view({"get": "artifacts_xml"})
invoice_pdf = NfceInvoiceViewSet.as_view({"get": "artifacts_pdf"})

urlpatterns = [
    path("nfce/gate/", NfceGateView.as_view(), name="nfce-gate"),
    path("nfce/config/", NfceConfigView.as_view(), name="nfce-config"),
    path("nfce/policy/preview", NfcePolicyPreviewView.as_view(), name="nfce-policy-preview"),
    path("nfce/checkout", NfceCheckoutView.as_view(), name="nfce-checkout"),
    path("nfce/invoices/", invoice_list, name="nfce-invoices"),
    path("nfce/invoices/<uuid:pk>/", invoice_detail, name="nfce-invoice-detail"),
    path("nfce/invoices/<uuid:pk>/items", invoice_items, name="nfce-invoice-items"),
    path("nfce/invoices/<uuid:pk>/validate", invoice_validate, name="nfce-invoice-validate"),
    path("nfce/invoices/<uuid:pk>/emit", invoice_emit, name="nfce-invoice-emit"),
    path("nfce/invoices/<uuid:pk>/cancel", invoice_cancel, name="nfce-invoice-cancel"),
    path("nfce/invoices/<uuid:pk>/events", invoice_events, name="nfce-invoice-events"),
    path(
        "nfce/invoices/<uuid:pk>/artifacts/xml",
        invoice_xml,
        name="nfce-invoice-xml",
    ),
    path(
        "nfce/invoices/<uuid:pk>/artifacts/pdf",
        invoice_pdf,
        name="nfce-invoice-pdf",
    ),
]
