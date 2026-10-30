from django.urls import path
from . import views

app_name = "billing"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("customer-lookup/", views.customer_lookup, name="customer_lookup"),
    path("new/", views.new_order, name="new"),
    path("settings/", views.settings_view, name="settings"),
    path("orders/<int:pk>/", views.order_detail, name="order"),
    path("orders/<int:pk>/payment/", views.order_payment, name="payment"),
    path("orders/<int:pk>/bill/", views.order_bill, name="issue"),
    path("bills/<int:pk>/", views.bill_detail, name="bill"),
    path("<slug:channel>/", views.channel_orders, name="channel"),
]
