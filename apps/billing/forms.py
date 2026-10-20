"""Staff order capture; prices always come from the kitchen catalog."""
import re
from django import forms
from django.forms import formset_factory
from apps.catalog.models import MenuItem
from apps.delivery.models import DeliveryZone


class ManualOrderForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    channel = forms.ChoiceField(choices=[("manual", "Manual / phone / walk-in"), ("whatsapp", "WhatsApp booking entered by staff")])
    name = forms.CharField(max_length=120, label="Customer name")
    phone = forms.CharField(max_length=20, label="Customer phone")
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    zone = forms.ModelChoiceField(queryset=DeliveryZone.all_tenants.none(), required=False,
        help_text="Leave empty for collection. Delivery fee and minimum come from the selected area.")
    payment_mode = forms.ChoiceField(choices=[("manual", "UPI / cash / other payment recorded by staff"), ("cod", "Cash on delivery")])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["zone"].queryset = DeliveryZone.objects.filter(active=True)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "o-input")

    def clean_phone(self):
        phone = re.sub(r"[\s()+-]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"[0-9]{10,15}", phone):
            raise forms.ValidationError("Enter a phone number with 10 to 15 digits.")
        return phone

    def clean(self):
        data = super().clean()
        if data.get("zone") and not data.get("address"):
            self.add_error("address", "Enter a delivery address for this delivery area.")
        return data


class OrderLineForm(forms.Form):
    item = forms.ModelChoiceField(queryset=MenuItem.all_tenants.none())
    quantity = forms.IntegerField(min_value=1, max_value=999, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = MenuItem.objects.filter(active=True).order_by("name")
        for field in self.fields.values():
            field.widget.attrs["class"] = "o-input"


OrderLines = formset_factory(OrderLineForm, extra=1, min_num=1, validate_min=True,
                            max_num=50, validate_max=True, absolute_max=50, can_delete=True)
