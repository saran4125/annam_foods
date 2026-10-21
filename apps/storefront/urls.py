from django.urls import path

from . import views, checkout_views

app_name = "storefront"

urlpatterns = [
    path("", views.home, name="home"),
    path("menu/", views.menu, name="menu"),
    path("shop/", views.shop, name="shop"),
    path("shop/<slug:slug>/", views.shop, name="shop_category"),
    path("item/<int:pk>/", views.item_detail, name="item"),
    path("cart/", views.cart_detail, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/clear/", views.cart_clear, name="cart_clear"),
    path("cart/pincode/", views.cart_set_pincode, name="cart_pincode"),
    path("checkout/", checkout_views.checkout, name="checkout"),
    path("checkout/complete/<uuid:reference>/", checkout_views.complete, name="checkout_complete"),
    path("about/", views.about, name="about"),
    path("p/<slug:slug>/", views.page_detail, name="page"),
]
