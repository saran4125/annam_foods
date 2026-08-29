from django.urls import path

from . import views

app_name = "storefront"

urlpatterns = [
    path("", views.home, name="home"),
    path("menu/", views.menu, name="menu"),
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/pincode/", views.cart_set_pincode, name="cart_pincode"),
    path("p/<slug:slug>/", views.page_detail, name="page"),
]
