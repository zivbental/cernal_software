from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.html import format_html

from apps.accounts.models import User
from apps.accounts.services import approve_user


class PendingApprovalFilter(admin.SimpleListFilter):
    """Approving accounts is the workflow, so it gets its own filter rather than
    hiding behind the generic `is_active` checkbox."""

    title = "approval"
    parameter_name = "approval"

    def lookups(self, request, model_admin):
        return [("pending", "Waiting for approval"), ("approved", "Approved")]

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.filter(is_active=False)
        if self.value() == "approved":
            return queryset.filter(is_active=True)
        return queryset


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "full_name",
        "approval_state",
        "is_staff",
        "date_joined",
    )
    list_filter = (PendingApprovalFilter, "is_staff", "is_superuser", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("is_active", "-date_joined")
    actions = ("approve_selected",)

    @admin.display(description="Name")
    def full_name(self, obj) -> str:
        return obj.get_full_name() or "—"

    @admin.display(description="Approval", ordering="is_active")
    def approval_state(self, obj) -> str:
        if obj.is_active:
            return format_html('<span style="color:#15803d">{}</span>', "approved")
        return format_html('<b style="color:#b45309">{}</b>', "waiting for approval")

    @admin.action(description="Approve selected accounts")
    def approve_selected(self, request, queryset):
        approved = sum(approve_user(user) for user in queryset)
        skipped = queryset.count() - approved

        if approved:
            self.message_user(
                request,
                f"Approved {approved} account{'s' if approved != 1 else ''}. They can sign in now.",
                messages.SUCCESS,
            )
        if skipped:
            self.message_user(request, f"{skipped} were already approved.", messages.INFO)

    def changelist_view(self, request, extra_context=None):
        """Surface the pending count, so nobody is left waiting unnoticed."""
        waiting = User.objects.filter(is_active=False).count()
        if waiting and not request.GET.get("approval"):
            self.message_user(
                request,
                f"{waiting} account{'s are' if waiting != 1 else ' is'} waiting for "
                "approval — filter by Approval → Waiting for approval.",
                messages.WARNING,
            )
        return super().changelist_view(request, extra_context)
