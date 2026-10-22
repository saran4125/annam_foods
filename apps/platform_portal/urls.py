"""Compatibility URLs only: no SEER login, workspace, provisioning or domain UI."""
from django.urls import path, re_path
from apps.payments.views import webhook as razorpay_webhook
from apps.content.image_views import storefront_image
from .integration_views import retired_page, tenant_meta_webhook, tenant_n8n_webhook

app_name = "portal"
urlpatterns = [
    path("assets/<slug:slug>/<uuid:pk>/", storefront_image, name="storefront_image"),
    path("webhooks/<slug:slug>/razorpay/<str:mode>/", razorpay_webhook, name="razorpay_webhook"),
    path("webhooks/<slug:slug>/whatsapp/", tenant_meta_webhook, name="tenant_meta_webhook"),
    path("webhooks/<slug:slug>/whatsapp/n8n/", tenant_n8n_webhook, name="tenant_n8n_webhook"),
    re_path(r"^(?P<path>.*)$", retired_page, name="retired"),
]
