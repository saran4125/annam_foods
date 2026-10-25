from django import forms
from django.core.exceptions import ValidationError
from apps.delivery.services import normalise_pincode


class CheckoutForm(forms.Form):
    name = forms.CharField(max_length=120, label='Full name', widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    phone = forms.CharField(max_length=20, label='Mobile number', widget=forms.TextInput(attrs={'type': 'tel', 'autocomplete': 'tel'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    pincode = forms.CharField(max_length=10, label='Delivery pincode', widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'postal-code'}))
    state = forms.ChoiceField(required=False, choices=[('Tamil Nadu', 'Tamil Nadu')], initial='Tamil Nadu', label='State')
    zone_id = forms.ChoiceField(required=False, label='Delivery area')
    line1 = forms.CharField(max_length=200, label='Door number, building and street', widget=forms.TextInput(attrs={'autocomplete': 'address-line1'}))
    line2 = forms.CharField(max_length=200, required=False, label='Area / locality', widget=forms.TextInput(attrs={'autocomplete': 'address-line2'}))
    city = forms.CharField(max_length=80, label='Town / city', widget=forms.TextInput(attrs={'autocomplete': 'address-level2'}))
    landmark = forms.CharField(max_length=120, required=False)

    payment_method = forms.ChoiceField(required=False, label="Payment method")

    def __init__(self, *args, cart, accepted_shop_order=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.cart_tenant = cart.request.tenant
        self.fields['pincode'].required = not (cart.is_courier or accepted_shop_order)
        from apps.payments.services import payment_choices
        choices = payment_choices(cart.request.tenant)
        self.fields["payment_method"].choices = choices
        self.fields["payment_method"].initial = choices[0][0] if choices else ""
        from apps.delivery.services import zones_for_pincode
        pin = self.data.get('pincode', cart.pincode) if self.is_bound else cart.pincode
        zones = [] if cart.is_courier else zones_for_pincode(pin, cart.slot_key)
        self.fields['zone_id'].choices = [('', 'Choose your area')] + [(str(z.pk), z.area_name) for z in zones]
        self.multiple_areas = len(zones) > 1
        self.fields['zone_id'].required = self.multiple_areas
        if not self.multiple_areas:
            self.fields['zone_id'] = forms.CharField(required=False, widget=forms.HiddenInput())
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'checkout-input')

    def clean_payment_method(self):
        from apps.payments.services import payment_choices
        choices = payment_choices(self.cart_tenant)
        return self.cleaned_data.get("payment_method") or (choices[0][0] if choices else "")

    def clean_zone_id(self):
        return self.cleaned_data['zone_id'] if self.multiple_areas else ''

    def clean_pincode(self):
        pin = normalise_pincode(self.cleaned_data['pincode'])
        if not pin and not self.fields['pincode'].required:
            return ''
        if len(pin) != 6 or pin[0] == '0':
            raise ValidationError('Enter a valid six-digit pincode.')
        return pin

    def clean_phone(self):
        import re
        raw = self.cleaned_data['phone']
        if not re.fullmatch(r'\+?[0-9 ()-]+', raw):
            raise ValidationError('Enter a valid Indian mobile number.')
        number = re.sub(r'\D', '', raw)
        if len(number) == 12 and number.startswith('91'):
            number = number[2:]
        if not re.fullmatch(r'[6-9][0-9]{9}', number):
            raise ValidationError('Enter a valid ten-digit Indian mobile number.')
        return '91' + number
