from django.db import models
from django.utils import timezone

from apps.tenancy.managers import TenantOwnedModel


class Page(TenantOwnedModel):
    """A page the owner writes himself.

    This is what answers "can we add a festival offer page later?" — yes, he
    writes it and it appears. Delivery cashback terms, refund policy, about,
    contact: all pages, none of them code, none of them a deploy.
    """

    slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=140)
    body_md = models.TextField(
        blank=True, verbose_name="body", help_text="Markdown. Headings, lists and links work."
    )
    seo_description = models.CharField(max_length=200, blank=True)
    published = models.BooleanField(default=False)
    show_in_nav = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["sort", "title"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "slug"], name="uniq_tenant_page_slug")
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        return super().save(*args, **kwargs)

    @property
    def body_html(self):
        import markdown

        from .services import sanitize_html

        rendered = markdown.markdown(
            self.body_md, extensions=["extra", "sane_lists", "nl2br"]
        )
        return sanitize_html(rendered)


class Banner(TenantOwnedModel):
    """Promo strip on the home page."""

    title = models.CharField(max_length=140)
    subtitle = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="banners/", blank=True)
    link = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["sort"]

    def __str__(self):
        return self.title
