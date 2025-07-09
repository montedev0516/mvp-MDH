from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from fleet.models.driver import Driver, DriverEmployment, EmploymentStatus, DutyStatus


class Command(BaseCommand):
    help = 'Fix Kelly Smith and other drivers missing employment records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.SUCCESS('🔍 Looking for Kelly Smith and other drivers missing employment records...')
        )
        
        # Find Kelly Smith specifically
        kelly_drivers = Driver.objects.filter(
            first_name__icontains='kelly', 
            last_name__icontains='smith'
        )
        
        if kelly_drivers.exists():
            for kelly in kelly_drivers:
                self.stdout.write(f'\n👤 Found Kelly: {kelly.first_name} {kelly.last_name} (ID: {kelly.id})')
                self.stdout.write(f'   - is_active: {kelly.is_active}')
                self.stdout.write(f'   - termination_date: {kelly.termination_date}')
                self.stdout.write(f'   - tenant: {kelly.tenant}')
                self.stdout.write(f'   - hire_date: {kelly.hire_date}')
                
                # Check employment record
                try:
                    employment = kelly.driveremployment
                    self.stdout.write(f'   ✅ Employment record exists: {employment.employment_status}')
                except DriverEmployment.DoesNotExist:
                    self.stdout.write('   ❌ No employment record found')
                    
                    if not dry_run:
                        try:
                            # Check validation conditions
                            if not kelly.is_active:
                                self.stdout.write(f'   ⚠️  Driver is not active: {kelly.is_active}')
                                continue
                                
                            if kelly.termination_date and kelly.termination_date <= timezone.now().date():
                                self.stdout.write(f'   ⚠️  Driver has been terminated: {kelly.termination_date}')
                                continue
                            
                            # Create employment record
                            employment = DriverEmployment.objects.create(
                                driver=kelly,
                                tenant=kelly.tenant,
                                employment_status=EmploymentStatus.ACTIVE,
                                duty_status=DutyStatus.AVAILABLE,
                            )
                            self.stdout.write(f'   ✅ Created employment record (ID: {employment.id})')
                            
                        except Exception as e:
                            self.stdout.write(f'   ❌ Failed to create employment record: {str(e)}')
                            import traceback
                            self.stdout.write(traceback.format_exc())
                    else:
                        self.stdout.write('   🧪 DRY RUN - Would create employment record')
        else:
            self.stdout.write('❌ No driver found with name containing "Kelly Smith"')
        
        # Also check all drivers without employment records
        self.stdout.write('\n🔍 Checking all drivers without employment records...')
        
        drivers_without_employment = Driver.objects.filter(
            driveremployment__isnull=True
        ).select_related('tenant')
        
        if drivers_without_employment.exists():
            self.stdout.write(f'Found {len(drivers_without_employment)} drivers without employment records:')
            
            for driver in drivers_without_employment:
                self.stdout.write(f'  - {driver.first_name} {driver.last_name} (Tenant: {driver.tenant.name})')
                
                if not dry_run:
                    try:
                        # Determine employment status
                        if driver.termination_date and driver.termination_date <= timezone.now().date():
                            employment_status = EmploymentStatus.TERMINATED
                            duty_status = DutyStatus.UNASSIGNED
                        elif not driver.is_active:
                            employment_status = EmploymentStatus.INACTIVE
                            duty_status = DutyStatus.UNASSIGNED
                        else:
                            employment_status = EmploymentStatus.ACTIVE
                            duty_status = DutyStatus.AVAILABLE
                        
                        # Create employment record
                        DriverEmployment.objects.create(
                            driver=driver,
                            tenant=driver.tenant,
                            employment_status=employment_status,
                            duty_status=duty_status,
                        )
                        
                        self.stdout.write(f'    ✅ Created employment record')
                        
                    except Exception as e:
                        self.stdout.write(f'    ❌ Failed: {str(e)}')
        else:
            self.stdout.write('✅ All drivers have employment records!')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('\n🧪 DRY RUN - No changes made. Run without --dry-run to apply fixes.')
            ) 