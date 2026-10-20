"""Write-only connection form and connection status, without returning stored secrets."""
import ipaddress
from urllib.parse import urlsplit
from django import forms
from django.core.exceptions import ValidationError
from apps.tenancy.models import TenantSecrets, MessageProvider


def validate_webhook_url(value):
    if not value:
        return
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None, 443):
        raise ValidationError("Use a public HTTPS webhook URL without login details, fragment or custom port.")
    if host == "localhost" or "." not in host or host.endswith((".local", ".localhost", ".internal")):
        raise ValidationError("Use a public n8n HTTPS hostname.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return
    if not address.is_global:
        raise ValidationError("Private network addresses are not supported.")


class WhatsAppConnectionForm(forms.Form):
    phone_number_id = forms.RegexField(r"^[0-9]{1,40}$", max_length=40, label="Meta phone number ID")
    waba_id = forms.RegexField(r"^[0-9]{1,40}$", max_length=40, required=False, label="WhatsApp Business Account ID")
    provider = forms.ChoiceField(choices=[(MessageProvider.N8N, "Keep n8n automation"), (MessageProvider.META_CLOUD, "Send directly through Meta"), (MessageProvider.CONSOLE, "Not connected — display only")], label="Staff reply sender")
    verify_token = forms.CharField(max_length=80, required=False, widget=forms.PasswordInput, help_text="Enter the same verification token in Meta. Leave blank to keep the saved value.")
    app_secret = forms.CharField(max_length=255, required=False, widget=forms.PasswordInput, label="Meta app secret", help_text="Used to verify signed Meta webhooks. Leave blank to retain.")
    sync_token = forms.CharField(min_length=24, max_length=255, required=False, widget=forms.PasswordInput, label="n8n inbox sync token", help_text="Choose a random token of at least 24 characters; store the same token in n8n Header Auth. Leave blank to retain.")
    n8n_send_url = forms.URLField(required=False, label="n8n send workflow URL", validators=[validate_webhook_url], help_text="Existing send workflow accepting the app's graph message envelope.")
    n8n_receive_url = forms.URLField(required=False, label="n8n automation receive URL (optional)", validators=[validate_webhook_url], help_text="Only when Meta points here: forward verified events to a separate n8n HTTP Webhook, not its WhatsApp Trigger callback.")
    n8n_auth_token = forms.CharField(max_length=255, required=False, widget=forms.PasswordInput, label="n8n workflow bearer token", help_text="Authenticates platform requests to the n8n send/receive workflows. Leave blank to retain.")
    meta_token = forms.CharField(max_length=4096, required=False, widget=forms.PasswordInput, label="Meta access token (optional with n8n)", help_text="Needed for direct sending or authenticated media previews. Leave blank to retain.")

    def __init__(self, *args, connection, **kwargs):
        self.connection = connection
        initial = {"phone_number_id": connection.wa_phone_number_id, "waba_id": connection.wa_waba_id,
                   "provider": connection.wa_provider if connection.wa_phone_number_id else MessageProvider.N8N,
                   "n8n_send_url": connection.n8n_send_url, "n8n_receive_url": connection.n8n_receive_url}
        super().__init__(*args, initial=initial, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "o-input"
        for name in ("verify_token", "app_secret", "sync_token", "n8n_auth_token", "meta_token"):
            self.fields[name].widget.attrs["autocomplete"] = "new-password"

    def clean(self):
        data = super().clean()
        if data.get("provider") == MessageProvider.N8N and not data.get("n8n_send_url"):
            self.add_error("n8n_send_url", "Provide the n8n send webhook, or select display-only until it is connected.")
        if (data.get("provider") == MessageProvider.N8N or data.get("n8n_receive_url")) and not (data.get("n8n_auth_token") or self.connection._n8n_auth_token):
            self.add_error("n8n_auth_token", "Set a bearer token for the n8n workflows; configure the same Header Auth credential in n8n.")
        if data.get("provider") == MessageProvider.META_CLOUD and not (data.get("meta_token") or self.connection._wa_token):
            self.add_error("meta_token", "A Meta access token is required for direct sending.")
        return data

    def save(self):
        data = self.cleaned_data
        s = self.connection
        s.wa_phone_number_id, s.wa_waba_id, s.wa_provider = data["phone_number_id"], data["waba_id"], data["provider"]
        s.n8n_send_url, s.n8n_receive_url = data["n8n_send_url"], data["n8n_receive_url"]
        for form_name, attribute in [("verify_token", "wa_verify_token"), ("app_secret", "wa_app_secret"),
                                     ("sync_token", "wa_sync_token"), ("n8n_auth_token", "n8n_auth_token"), ("meta_token", "wa_token")]:
            if data.get(form_name):
                setattr(s, attribute, data[form_name])
        s.save()
        return s
