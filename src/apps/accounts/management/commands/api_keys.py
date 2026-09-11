"""List a user's API keys from the terminal (ADR 0006). Never shows a secret.

./do keys alice
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "List a user's API keys (prefix, scopes, status — never the secret)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("username")

    def handle(self, *args, **options) -> None:
        model = get_user_model()
        user = model.objects.filter(username__iexact=options["username"]).first()
        if user is None:
            raise CommandError(f"No account named '{options['username']}'.")

        keys = list(user.api_keys.all())
        if not keys:
            self.stdout.write(f"{user.username} has no API keys.")
            return

        self.stdout.write(f"{len(keys)} key(s) for {user.username}:\n")
        for key in keys:
            status = "revoked" if key.revoked_at else ("active" if key.is_active else "expired")
            last_used = key.last_used_at.strftime("%Y-%m-%d %H:%M") if key.last_used_at else "never"
            self.stdout.write(
                f"  {key.prefix:<16} {key.label:<24} {','.join(key.scopes):<14} "
                f"{status:<8} last used {last_used}"
            )
