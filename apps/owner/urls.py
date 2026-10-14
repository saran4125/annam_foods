from django.urls import path

from . import views

app_name = "owner"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("orders/", views.orders, name="orders"),
    path("orders/<int:pk>/", views.order_detail, name="order"),
    path("settings/", views.settings_view, name="settings"),
    path("<slug:key>/", views.resource_list, name="list"),
    path("<slug:key>/new/", views.resource_edit, name="new"),
    path("<slug:key>/<int:pk>/", views.resource_edit, name="edit"),
    path("<slug:key>/<int:pk>/delete/", views.resource_delete, name="delete"),
    path("<slug:key>/<int:pk>/toggle/", views.resource_toggle, name="toggle"),
]
