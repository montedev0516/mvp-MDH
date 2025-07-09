from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.core.cache import cache
from django.db import connection


class Command(BaseCommand):
    help = 'Initialize database with all required tables and setup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-cache',
            action='store_true',
            help='Skip cache table creation',
        )

    def handle(self, *args, **options):
        self.stdout.write('🚀 Starting database initialization...')
        
        # Run migrations
        self.stdout.write('📋 Running migrations...')
        call_command('migrate', verbosity=0)
        self.stdout.write(self.style.SUCCESS('✅ Migrations completed'))
        
        # Create cache table if not skipped
        if not options['skip_cache']:
            self.stdout.write('💾 Creating cache table...')
            try:
                call_command('createcachetable', verbosity=0)
                self.stdout.write(self.style.SUCCESS('✅ Cache table created'))
                
                # Test cache functionality
                cache.set('init_test', 'success', 10)
                if cache.get('init_test') == 'success':
                    self.stdout.write(self.style.SUCCESS('✅ Cache functionality verified'))
                    cache.delete('init_test')
                else:
                    self.stdout.write(self.style.WARNING('⚠️  Cache test failed'))
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ Cache table creation failed: {e}'))
        
        # Collect static files
        self.stdout.write('📦 Collecting static files...')
        call_command('collectstatic', '--noinput', verbosity=0)
        self.stdout.write(self.style.SUCCESS('✅ Static files collected'))
        
        self.stdout.write(self.style.SUCCESS('🎉 Database initialization completed successfully!')) 