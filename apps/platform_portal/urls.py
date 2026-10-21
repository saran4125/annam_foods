from django.urls import path
from . import views
from . import domain_views
from apps.payments.views import webhook as razorpay_webhook
from apps.content.image_views import storefront_image

app_name = "portal"
urlpatterns = [
    path("assets/<slug:slug>/<uuid:pk>/", storefront_image, name="storefront_image"),
    path("", views.home, name="home"),
    path("about/", views.landing, name="landing"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("admin/", views.admin_dashboard, name="admin"),
    path("admin/kitchens/new/", views.create_kitchen, name="create"),
    path("admin/kitchens/<slug:slug>/", views.kitchen_admin, name="kitchen_admin"),
    path("workspaces/<slug:slug>/", views.workspace, name="workspace"),
    path("workspaces/<slug:slug>/domains/", domain_views.domains, name="domains"),
    path("domains/allow-certificate/", domain_views.allow_certificate, name="allow_certificate"),
    path("invitations/accept/", views.accept_invitation, name="accept_invitation"),
    path("webhooks/<slug:slug>/razorpay/<str:mode>/", razorpay_webhook, name="razorpay_webhook"),
    path("webhooks/<slug:slug>/whatsapp/", views.tenant_meta_webhook, name="tenant_meta_webhook"),
    path("webhooks/<slug:slug>/whatsapp/n8n/", views.tenant_n8n_webhook, name="tenant_n8n_webhook"),
]
