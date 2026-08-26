from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model.

    Intentionally empty. Defined at Step 0, before the first migration, because
    swapping AUTH_USER_MODEL after migrations exist is a painful Django migration.
    See docs/architecture.md §5.
    """
