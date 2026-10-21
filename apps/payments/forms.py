import re
from django import forms
from .models import RazorpayConnection


class RazorpaySettingsForm(forms.Form):
    mode = forms.ChoiceField(choices=[('test', 'Test mode'), ('live', 'Live mode')], widget=forms.HiddenInput)
    key_id = forms.CharField(max_length=80, label='Razorpay Key ID')
    key_secret = forms.CharField(required=False, min_length=8, max_length=255, label='Key Secret',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}))
    webhook_secret = forms.CharField(required=False, min_length=16, max_length=255, label='Webhook secret',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Choose at least 16 characters and enter the same secret in your Razorpay webhook settings.')
    enabled = forms.BooleanField(required=False, label='Enable Razorpay for website checkout')
    live_confirm = forms.BooleanField(required=False, label='I confirm this kitchen’s Razorpay account is activated and I want to accept real payments')

    def __init__(self, *args, mode='test', **kwargs):
        self.selected_mode = mode
        connection = RazorpayConnection.objects.filter(mode=mode).first()
        self.connection = connection
        super().__init__(*args, initial={'mode': mode, 'key_id': connection.key_id if connection else '',
                                         'enabled': bool(connection and connection.enabled)}, **kwargs)
        if mode == 'test':
            self.fields['live_confirm'].widget = forms.HiddenInput()
        if connection:
            self.fields['key_secret'].help_text = 'Saved securely. Leave blank to keep it.' if connection._key_secret else ''
            self.fields['webhook_secret'].help_text += ' Leave blank to keep the saved secret.' if connection._webhook_secret else ''
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'o-input'

    def clean(self):
        data = super().clean()
        mode = data.get('mode')
        if mode not in ('test', 'live'):
            return data
        connection = RazorpayConnection.objects.filter(mode=mode).first()
        key = data.get('key_id', '')
        if not re.fullmatch(r'rzp_' + mode + r'_[A-Za-z0-9]+', key):
            self.add_error('key_id', 'Use a Key ID matching the selected test/live mode.')
        if not data.get('key_secret') and (not connection or not connection._key_secret):
            self.add_error('key_secret', 'Enter the Key Secret for this mode.')
        if connection and key != connection.key_id and not data.get('key_secret'):
            self.add_error('key_secret', 'Enter the matching Key Secret when changing the Key ID.')
        if not data.get('webhook_secret') and (not connection or not connection._webhook_secret):
            self.add_error('webhook_secret', 'Enter a webhook secret for this mode.')
        if mode == 'live' and data.get('enabled') and not data.get('live_confirm'):
            self.add_error('live_confirm', 'Confirm live payments before enabling this account.')
        return data
