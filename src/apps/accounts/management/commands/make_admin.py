"""Promote an account to a site administrator.

Solves the bootstrapping problem: accounts are admin-approved, so the very first person
has nobody to approve them. This activates and promotes an existing account without
touching its password — unlike `createsuperuser`, which needs a fresh one.

    ./do make-admin zivbental
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Activate an account and grant it staff and superuser rights."

    def add_arguments(self, parser) -> None:
        parser.add_argument("username", help="The account to promote.")
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Remove staff and superuser rights instead.",
        )

    def handle(self, *args, **options) -> None:
        model = get_user_model()
        username = options["username"]

        user = model.objects.filter(username__iexact=username).first()
        if user is None:
            self.stderr.write(self.style.ERROR(f"No account named '{username}'."))
            return

        if options["revoke"]:
            user.is_staff = False
            user.is_superuser = False
            user.save(update_fields=["is_staff", "is_superuser"])
            self.stdout.write(f"{user.username} is no longer an administrator.")
            return

        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_active", "is_staff", "is_superuser"])

        self.stdout.write(
            self.style.SUCCESS(
                f"{user.username} is now an administrator and can sign in at /admin/."
            )
        )
