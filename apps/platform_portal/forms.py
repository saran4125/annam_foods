from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from apps.tenancy.models import TenantStatus, TenantUserRole
from apps.tenancy.presets import preset_names
from .services import normalized_slug


class Styled:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "p-checkbox" if isinstance(field.widget, forms.CheckboxInput) else "p-input")


class PlatformLoginForm(Styled, AuthenticationForm):
    pass


class ActivateOwnerForm(Styled, SetPasswordForm):
    pass


class CreateKitchenForm(Styled, forms.Form):
    name = forms.CharField(max_length=120, label="Kitchen name")
    slug = forms.CharField(max_length=60, label="Kitchen address", help_text="A unique name such as annam-foods. It also identifies the workspace.")
    owner_email = forms.EmailField(label="Owner email")
    preset = forms.ChoiceField(label="Website starting point")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["preset"].choices = [(name, name.replace("-", " ").title()) for name in preset_names()]

    def clean_slug(self):
        return normalized_slug(self.cleaned_data["slug"])


class InviteOwnerForm(Styled, forms.Form):
    email = forms.EmailField(label="Team member email")
    role = forms.ChoiceField(choices=TenantUserRole.choices, initial="owner", label="Kitchen role", help_text="Each invited member gets access to this kitchen’s existing management tools.")


class KitchenStatusForm(Styled, forms.Form):
    status = forms.ChoiceField(choices=[(TenantStatus.PROVISIONING, "Setup in progress"), (TenantStatus.ACTIVE, "Active"), (TenantStatus.SUSPENDED, "Ordering suspended")])


class KitchenFeaturesForm(Styled, forms.Form):
    website_ordering = forms.BooleanField(required=False, label="Website ordering enabled", help_text="Allow the existing storefront ordering controls. Checkout and payments are still separate integrations.")
    snacks_courier = forms.BooleanField(required=False, label="Courier shop enabled", help_text="Show packed/courier products in the storefront shop.")


class AddDomainForm(Styled, forms.Form):
    hostname = forms.CharField(max_length=253, label="Custom domain", help_text="For example, www.yourkitchen.com. Add the root domain separately if you also want it connected.", widget=forms.TextInput(attrs={"class": "o-input", "placeholder": "www.yourkitchen.com", "autocapitalize": "none", "spellcheck": "false", "autocomplete": "off"}))

    def clean_hostname(self):
        from .domain_services import normalize_hostname
        return normalize_hostname(self.cleaned_data["hostname"])
