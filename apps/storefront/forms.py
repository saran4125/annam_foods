from django import forms
from django.core.exceptions import ValidationError
from apps.delivery.services import normalise_pincode


class CheckoutForm(forms.Form):
    name = forms.CharField(max_length=120, label='Full name', widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    phone = forms.CharField(max_length=20, label='Mobile number', widget=forms.TextInput(attrs={'type': 'tel', 'autocomplete': 'tel'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    pincode = forms.CharField(max_length=10, label='Delivery pincode', widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'postal-code'}))
    state = forms.CharField(required=False, max_length=100, initial='Tamil Nadu', label='State / province')
    country = forms.CharField(required=False, max_length=80, initial='India', label='Country')
    zone_id = forms.ChoiceField(required=False, label='Delivery area')
    line1 = forms.CharField(max_length=200, label='Door number, building and street', widget=forms.TextInput(attrs={'autocomplete': 'address-line1'}))
    line2 = forms.CharField(max_length=200, required=False, label='Area / locality', widget=forms.TextInput(attrs={'autocomplete': 'address-line2'}))
    city = forms.CharField(max_length=80, label='Town / city', widget=forms.TextInput(attrs={'autocomplete': 'address-level2'}))
    landmark = forms.CharField(max_length=120, required=False)

    payment_method = forms.ChoiceField(required=False, label="Payment method")

    def __init__(self, *args, cart, accepted_shop_order=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.cart_tenant = cart.request.tenant
        self.is_shop = cart.is_courier or accepted_shop_order
        self.fields['pincode'].required = not (cart.is_courier or accepted_shop_order)
        from apps.payments.services import payment_choices
        choices = payment_choices(cart.request.tenant)
        self.fields["payment_method"].choices = choices
        self.fields["payment_method"].initial = choices[0][0] if choices else ""
        from apps.delivery.policies import eligible_zones
        pin = self.data.get('pincode', cart.pincode) if self.is_bound else cart.pincode
        zones = eligible_zones(pin,cart.slot_keys or ["snacks"])
        self.fields['zone_id'].choices = [('', 'Choose your area')] + [(str(z.pk), f'{z.area_name} – ₹{z.delivery_fee:.2f}') for z in zones]
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
        raw = self.cleaned_data['pincode']
        if self.is_shop and self.data.get('country','India').strip().casefold() not in ('','india'):
            return raw.strip()
        pin = normalise_pincode(raw)
        if not pin and not self.fields['pincode'].required:
            return ''
        if len(pin) != 6 or pin[0] == '0':
            raise ValidationError('Enter a valid six-digit pincode.')
        return pin

    def clean_phone(self):
        import re
        raw = self.cleaned_data['phone']
        if self.is_shop and self.data.get('country','India').strip().casefold() not in ('','india'):
            if not re.fullmatch(r'\+[1-9][0-9]{6,14}',raw):
                raise ValidationError('Enter an international phone number including + and country code.')
            return raw.lstrip('+')
        if not re.fullmatch(r'\+?[0-9 ()-]+', raw):
            raise ValidationError('Enter a valid Indian mobile number.')
        number = re.sub(r'\D', '', raw)
        if len(number) == 12 and number.startswith('91'):
            number = number[2:]
        if not re.fullmatch(r'[6-9][0-9]{9}', number):
            raise ValidationError('Enter a valid ten-digit Indian mobile number.')
        return '91' + number

    def clean(self):
        data = super().clean()
        if not self.is_shop and ((data.get('country') or 'India').casefold() != 'india' or (data.get('state') or 'Tamil Nadu').casefold() != 'tamil nadu'):
            raise ValidationError('Fresh meals are delivered only to approved local delivery areas in Tamil Nadu.')
        data['country'] = data.get('country') or 'India'
        data['state'] = data.get('state') or ('Tamil Nadu' if data['country'].casefold() == 'india' else '')
        return data
