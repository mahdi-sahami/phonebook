import csv

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import Contact


# ─── Custom List Filters ──────────────────────────────────────────────────────

class HasEmailFilter(admin.SimpleListFilter):
    title = _('has email')
    parameter_name = 'has_email'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        filled = Q(email__isnull=False) & ~Q(email='')
        if self.value() == 'yes':
            return queryset.filter(filled)
        if self.value() == 'no':
            return queryset.exclude(filled)
        return queryset


class HasAddressFilter(admin.SimpleListFilter):
    title = _('has address')
    parameter_name = 'has_address'

    def lookups(self, request, model_admin):
        return (
            ('yes', _('Yes')),
            ('no', _('No')),
        )

    def queryset(self, request, queryset):
        filled = Q(address__isnull=False) & ~Q(address='')
        if self.value() == 'yes':
            return queryset.filter(filled)
        if self.value() == 'no':
            return queryset.exclude(filled)
        return queryset


# ─── Custom Actions ───────────────────────────────────────────────────────────

@admin.action(description=_('Export selected contacts to CSV'))
def export_contacts_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="contacts.csv"'
    writer = csv.writer(response)
    writer.writerow([_('Owner'), _('Name'), _('Phone'), _('Email'), _('Address')])
    for contact in queryset.select_related('owner').order_by('owner__username', 'name'):
        writer.writerow([
            contact.owner.username,
            contact.name,
            contact.phone,
            contact.email or '',
            contact.address or '',
        ])
    return response


# ─── Inline ───────────────────────────────────────────────────────────────────

class ContactInline(admin.TabularInline):
    model = Contact
    extra = 0
    fields = ('name', 'phone', 'email', 'address')
    show_change_link = True
    max_num = 30
    verbose_name_plural = _('Contacts')


# ─── Contact ModelAdmin ───────────────────────────────────────────────────────

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):

    # ── List view ──────────────────────────────────────────────────────────────
    list_display = (
        'name',
        'phone_display',
        'email_display',
        'address_icon',
        'owner_link',
        'owner_total_contacts',
    )
    list_display_links = ('name',)
    list_filter = (HasEmailFilter, HasAddressFilter, 'owner')
    search_fields = ('name', 'phone', 'email', 'address', 'owner__username')
    list_per_page = 25
    list_select_related = ('owner',)
    ordering = ('name',)
    empty_value_display = '—'
    show_full_result_count = True

    # ── Detail view ────────────────────────────────────────────────────────────
    fieldsets = (
        (_('Owner'), {
            'fields': ('owner',),
        }),
        (_('Contact Info'), {
            'fields': ('name', 'phone'),
        }),
        (_('Optional Info'), {
            'fields': ('email', 'address'),
            'classes': ('collapse',),
        }),
    )
    autocomplete_fields = ('owner',)

    # ── Actions ────────────────────────────────────────────────────────────────
    actions = (export_contacts_csv,)

    # ── Custom columns ─────────────────────────────────────────────────────────

    @admin.display(description=_('Phone'), ordering='phone')
    def phone_display(self, obj):
        return format_html('<a href="tel:{}">{}</a>', obj.phone, obj.phone)

    @admin.display(description=_('Email'), ordering='email')
    def email_display(self, obj):
        if obj.email:
            return format_html('<a href="mailto:{}">{}</a>', obj.email, obj.email)
        return self.empty_value_display

    @admin.display(description=_('Address'), boolean=True)
    def address_icon(self, obj):
        return bool(obj.address)

    @admin.display(description=_('Owner'), ordering='owner__username')
    def owner_link(self, obj):
        url = f'/admin/auth/user/{obj.owner.pk}/change/'
        return format_html('<a href="{}">{}</a>', url, obj.owner.username)

    @admin.display(description=_('Total Contacts'))
    def owner_total_contacts(self, obj):
        count = obj.owner.contacts.count()
        url = f'/admin/contacts/contact/?owner__id__exact={obj.owner.pk}'
        return format_html('<a href="{}">{}</a>', url, count)

    # ── Queryset & permissions ─────────────────────────────────────────────────

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(owner=request.user)
        return qs

    def get_fieldsets(self, request, obj=None):
        if not request.user.is_superuser:
            return (
                (_('Contact Info'), {'fields': ('name', 'phone')}),
                (_('Optional Info'), {
                    'fields': ('email', 'address'),
                    'classes': ('collapse',),
                }),
            )
        return super().get_fieldsets(request, obj)

    def save_model(self, request, obj, form, change):
        if not change and not request.user.is_superuser:
            obj.owner = request.user
        super().save_model(request, obj, form, change)


# ─── Extended User Admin ──────────────────────────────────────────────────────

class CustomUserAdmin(UserAdmin):
    inlines = (ContactInline,)
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'is_staff',
        'is_active',
        'contact_count',
        'date_joined',
    )
    list_filter = UserAdmin.list_filter + ('date_joined',)

    @admin.display(description=_('Contacts'), ordering='contact_count')
    def contact_count(self, obj):
        count = obj.contact_count
        url = f'/admin/contacts/contact/?owner__id__exact={obj.pk}'
        return format_html('<a href="{}">{}</a>', url, count)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(contact_count=Count('contacts'))


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# ─── Admin site branding ──────────────────────────────────────────────────────

admin.site.site_header = 'Contact Book Admin'
admin.site.site_title = 'Contact Book'
admin.site.index_title = 'Dashboard'
