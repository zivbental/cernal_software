"""List and approve pending accounts from the terminal.

Django admin is the normal route, but this exists so approving somebody does not require
a browser — useful over SSH on the VPS.

    ./do pending
    ./do approve alice bob
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.services import approve_user, pending_users


class Command(BaseCommand):
    help = "List accounts waiting for approval, or approve them by username."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--approve",
            nargs="*",
            metavar="USERNAME",
            help="Approve these accounts instead of listing.",
        )

    def handle(self, *args, **options) -> None:
        usernames = options.get("approve")

        if usernames is None:
            self._list()
            return

        if not usernames:
            self.stderr.write("Give at least one username: ./do approve <username>")
            return

        self._approve(usernames)

    def _list(self) -> None:
        waiting = list(pending_users())
        if not waiting:
            self.stdout.write("No accounts are waiting for approval.")
            return

        self.stdout.write(f"{len(waiting)} account(s) waiting for approval:\n")
        for user in waiting:
            name = user.get_full_name() or "—"
            self.stdout.write(
                f"  {user.username:<20} {user.email:<32} {name:<24} "
                f"requested {user.date_joined:%Y-%m-%d %H:%M}"
            )
        self.stdout.write("\nApprove with:  ./do approve <username> [username...]")

    def _approve(self, usernames: list[str]) -> None:
        model = get_user_model()

        for username in usernames:
            user = model.objects.filter(username__iexact=username).first()
            if user is None:
                self.stderr.write(self.style.ERROR(f"  {username}: no such account"))
                continue
            if approve_user(user):
                self.stdout.write(self.style.SUCCESS(f"  {user.username}: approved"))
            else:
                self.stdout.write(f"  {user.username}: already approved")
