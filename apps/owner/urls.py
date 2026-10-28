from django.urls import path

from . import views, report_views
from apps.payments import views as payment_views
from apps.messaging import inbox_views

app_name = "owner"

urlpatterns = [
    path("reports/", report_views.reports, name="reports"),
    path("orders/<int:pk>/courier/", report_views.courier_action, name="courier_action"),
    path("courier-notices/release/", report_views.release_notices, name="release_notices"),
    path("dishes/menu/", views.daily_menu, name="daily_menu"),
    path("whatsapp/", inbox_views.inbox, name="whatsapp"),
    path("whatsapp/settings/", inbox_views.connection_settings, name="whatsapp_settings"),
    path("whatsapp/<int:pk>/", inbox_views.inbox, name="whatsapp_conversation"),
    path("whatsapp/<int:pk>/reply/", inbox_views.reply, name="whatsapp_reply"),
    path("whatsapp/messages/<int:pk>/media/", inbox_views.media, name="whatsapp_media"),
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("orders/", views.orders, name="orders"),
    path("orders/<int:pk>/", views.order_detail, name="order"),
    path("billing/", views.billing_settings, name="billing_settings"),
    path("bills/<int:pk>/", views.bill_detail, name="bill"),
    path("orders/<int:pk>/bill/", views.order_bill, name="order_bill"),
    path("orders/<int:pk>/payment/", views.order_payment, name="order_payment"),
    path("payments/razorpay/", payment_views.connection_settings, name="razorpay_settings"),
    path("orders/<int:pk>/refund/", payment_views.refund, name="razorpay_refund"),
    path("checkout-settings/", views.checkout_settings, name="checkout_settings"),
    path("settings/", views.settings_view, name="settings"),
    path("<slug:key>/", views.resource_list, name="list"),
    path("<slug:key>/new/", views.resource_edit, name="new"),
    path("<slug:key>/<int:pk>/", views.resource_edit, name="edit"),
    path("<slug:key>/<int:pk>/delete/", views.resource_delete, name="delete"),
    path("<slug:key>/<int:pk>/toggle/", views.resource_toggle, name="toggle"),
]
