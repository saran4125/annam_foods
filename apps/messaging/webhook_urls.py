from django.urls import path
from . import webhooks

app_name = "whatsapp_webhooks"
urlpatterns = [path("", webhooks.meta_webhook, name="meta"), path("n8n/", webhooks.n8n_sync, name="n8n")]
