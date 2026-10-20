"""Write-only connection form and connection status, without returning stored secrets."""
import ipaddress
from urllib.parse import urlsplit
from django import forms
from django.core.exceptions import ValidationError


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
    """Only the requirements for mirroring the existing n8n conversations."""

    phone_number_id = forms.RegexField(
        r"^[0-9]{1,40}$", max_length=40, label="Meta phone number ID",
        help_text="Use the phone number ID from your existing n8n WhatsApp connection, not the phone number.")
    sync_token = forms.CharField(
        min_length=24, max_length=255, widget=forms.PasswordInput,
        label="n8n inbox sync token",
        help_text="Choose a random token of at least 24 characters. Use the same value in n8n Header Auth: Authorization: Bearer <token>.")

    def __init__(self, *args, connection, **kwargs):
        self.connection = connection
        super().__init__(*args, initial={"phone_number_id": connection.wa_phone_number_id}, **kwargs)
        self.fields["sync_token"].required = not bool(connection._wa_sync_token)
        if connection._wa_sync_token:
            self.fields["sync_token"].help_text = "A token is already saved. Leave blank to keep it, or enter a new token and update n8n to match."
        for field in self.fields.values():
            field.widget.attrs["class"] = "o-input"
        self.fields["sync_token"].widget.attrs["autocomplete"] = "new-password"

    def save(self):
        connection = self.connection
        connection.wa_phone_number_id = self.cleaned_data["phone_number_id"]
        fields = ["wa_phone_number_id"]
        if self.cleaned_data.get("sync_token"):
            connection.wa_sync_token = self.cleaned_data["sync_token"]
            fields.append("_wa_sync_token")
        connection.save(update_fields=fields)
        return connection
