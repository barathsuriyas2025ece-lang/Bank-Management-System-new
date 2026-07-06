from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User, Group
from django.shortcuts import redirect
from django.urls import reverse
from .models import Account, Transaction


class AccountRequiredAdminSite(AdminSite):
    # Standard admin behavior, allow staff members to login normally
    pass


site = AccountRequiredAdminSite()
site._registry = admin.site._registry.copy()  # Copy default registrations
admin.site = site  # Replace default admin site

# Register Account and Transaction with custom site
# Moved after class definitions


class AccountAdmin(admin.ModelAdmin):
    # display abdul, ram, barathsuriya
    list_display = ('account_number', 'name', 'balance', 'is_frozen')
    search_fields = ('account_number', 'name')
    actions = ['freeze_accounts', 'unfreeze_accounts']
    
    # Custom action to freeze accounts
    def freeze_accounts(self, request, queryset):
        updated = queryset.update(is_frozen=True)
        self.message_user(request, f'{updated} account(s) have been frozen.')
    freeze_accounts.short_description = "Freeze selected accounts"
    
    # Custom action to unfreeze accounts
    def unfreeze_accounts(self, request, queryset):
        updated = queryset.update(is_frozen=False)
        self.message_user(request, f'{updated} account(s) have been unfrozen.')
    unfreeze_accounts.short_description = "Unfreeze selected accounts"

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('account', 'type', 'amount', 'timestamp')
    list_filter = ('timestamp', 'type')


site.register(Account, AccountAdmin)
site.register(Transaction, TransactionAdmin)