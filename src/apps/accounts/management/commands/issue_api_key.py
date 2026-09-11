"""Mint an API key from the terminal (ADR 0006).

The secret is shown exactly once, here, and never stored — so this is the only place it
can ever be recovered. Session/admin issuance is the normal route (POST
/api/auth/keys); this exists for bootstrapping a script before a browser session is
convenient, e.g. over SSH on the VPS.

    ./do key alice laptop
    ./do key alice snakemake-prod --scopes read --expires-in-days 90
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import ApiKeyScope
from apps.accounts.services import RegistrationError, issue_api_key


class Command(BaseCommand):
    help = "Mint an API key for a user and print the secret once."

    def add_arguments(self, parser) -> None:
        parser.add_argument("username")
        parser.add_argument("label", help='e.g. "laptop", "snakemake-prod".')
        parser.add_argument(
            "--scopes",
            nargs="*",
            default=[ApiKeyScope.READ, ApiKeyScope.DESIGN],
            choices=ApiKeyScope.values,
        )
        parser.add_argument("--expires-in-days", type=int, default=None)

    def handle(self, *args, **options) -> None:
        model = get_user_model()
        user = model.objects.filter(username__iexact=options["username"]).first()
        if user is None:
            raise CommandError(f"No account named '{options['username']}'.")

        try:
            key, secret = issue_api_key(
                owner=user,
                label=options["label"],
                scopes=tuple(options["scopes"]),
                expires_in_days=options["expires_in_days"],
            )
        except RegistrationError as exc:
            raise CommandError(str(exc)) from None

        self.stdout.write(self.style.SUCCESS(f"Issued key '{key.label}' for {user.username}:"))
        self.stdout.write(f"\n  {secret}\n")
        self.stdout.write(
            self.style.WARNING("This secret is shown once and is not recoverable. Store it now.")
        )
