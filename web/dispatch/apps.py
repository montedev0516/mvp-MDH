"""Django app configuration for the dispatch app."""

from django.apps import AppConfig


class DispatchConfig(AppConfig):
    """Configuration for the dispatch app."""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dispatch'
    verbose_name = 'Dispatch Management'

    def ready(self):
        """Initialize app and register signals."""
        try:
            import dispatch.signals  # noqa
        except ImportError:
            pass
