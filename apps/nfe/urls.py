from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.nfe.views import NfeConfigView, NfeGateView, NfeInvoiceViewSet, NfeProductViewSet

router = DefaultRouter()
router.register("nfe/products", NfeProductViewSet, basename="nfe-products")

invoice_list = NfeInvoiceViewSet.as_view({"get": "list", "post": "create"})
invoice_detail = NfeInvoiceViewSet.as_view({"get": "retrieve"})
invoice_items = NfeInvoiceViewSet.as_view({"put": "items"})
invoice_validate = NfeInvoiceViewSet.as_view({"post": "validate"})
invoice_emit = NfeInvoiceViewSet.as_view({"post": "emit"})
invoice_cancel = NfeInvoiceViewSet.as_view({"post": "cancel"})
invoice_cce = NfeInvoiceViewSet.as_view({"post": "cce"})
invoice_discard = NfeInvoiceViewSet.as_view({"post": "discard"})
invoice_clone = NfeInvoiceViewSet.as_view({"post": "clone"})
invoice_events = NfeInvoiceViewSet.as_view({"get": "events"})
invoice_xml = NfeInvoiceViewSet.as_view({"get": "artifacts_xml"})
invoice_pdf = NfeInvoiceViewSet.as_view({"get": "artifacts_pdf"})
invoice_cce_xml = NfeInvoiceViewSet.as_view({"get": "artifacts_cce"})

urlpatterns = [
    path("nfe/gate/", NfeGateView.as_view(), name="nfe-gate"),
    path("nfe/config/", NfeConfigView.as_view(), name="nfe-config"),
    path("nfe/invoices/", invoice_list, name="nfe-invoices"),
    path("nfe/invoices/<uuid:pk>/", invoice_detail, name="nfe-invoice-detail"),
    path("nfe/invoices/<uuid:pk>/items", invoice_items, name="nfe-invoice-items"),
    path("nfe/invoices/<uuid:pk>/validate", invoice_validate, name="nfe-invoice-validate"),
    path("nfe/invoices/<uuid:pk>/emit", invoice_emit, name="nfe-invoice-emit"),
    path("nfe/invoices/<uuid:pk>/cancel", invoice_cancel, name="nfe-invoice-cancel"),
    path("nfe/invoices/<uuid:pk>/cce", invoice_cce, name="nfe-invoice-cce"),
    path("nfe/invoices/<uuid:pk>/discard", invoice_discard, name="nfe-invoice-discard"),
    path("nfe/invoices/<uuid:pk>/clone", invoice_clone, name="nfe-invoice-clone"),
    path("nfe/invoices/<uuid:pk>/events", invoice_events, name="nfe-invoice-events"),
    path("nfe/invoices/<uuid:pk>/artifacts/xml", invoice_xml, name="nfe-invoice-xml"),
    path("nfe/invoices/<uuid:pk>/artifacts/pdf", invoice_pdf, name="nfe-invoice-pdf"),
    path("nfe/invoices/<uuid:pk>/artifacts/cce", invoice_cce_xml, name="nfe-invoice-cce-xml"),
    *router.urls,
]
