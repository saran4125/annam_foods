from django import forms

from .crypto import mask
from .models import TenantSecrets

SECRET_FIELDS = [
    ("wa_token", "WhatsApp token"),
    ("wa_app_secret", "WhatsApp app secret"),
    ("n8n_auth_token", "n8n auth token"),
    ("razorpay_secret", "Razorpay key secret"),
    ("razorpay_webhook_secret", "Razorpay webhook secret"),
]


class TenantSecretsForm(forms.ModelForm):
    """Secrets go in; they never come back out.

    Each secret gets a write-only input and a masked, read-only display of
    what is currently stored. Leaving an input blank keeps the existing value.
    A compromised login must not be able to read the keys that move a client's
    money -- which is why there is no reveal toggle here.
    """

    class Meta:
        model = TenantSecrets
        fields = [
            "wa_provider", "wa_phone_number_id", "wa_waba_id", "wa_verify_token",
            "n8n_send_url", "razorpay_key_id", "razorpay_live_mode",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get("instance") or self.instance
        for name, label in SECRET_FIELDS:
            current = ""
            if instance and instance.pk:
                try:
                    current = mask(getattr(instance, name))
                except RuntimeError:
                    current = "(unreadable — wrong SECRETS_KEY)"
            self.fields[f"new_{name}"] = forms.CharField(
                label=label, required=False,
                widget=forms.PasswordInput(render_value=False),
                help_text=(f"Currently stored: {current}. Leave blank to keep it."
                           if current else "Not set."),
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        for name, _label in SECRET_FIELDS:
            value = self.cleaned_data.get(f"new_{name}")
            if value:
                setattr(instance, name, value)
        if commit:
            instance.save()
        return instance
