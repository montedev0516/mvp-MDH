from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from fleet.models import Driver, DriverEmployment, EmploymentStatus, DutyStatus


class Command(BaseCommand):
    help = 'Create missing DriverEmployment records for drivers'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--tenant-id',
            type=str,
            help='Fix only drivers for specific tenant ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        tenant_id = options.get('tenant_id')
        
        self.stdout.write(
            self.style.SUCCESS('🔍 Checking for drivers missing employment records...')
        )
        
        # Build query for drivers without employment records
        drivers_query = Driver.objects.filter(
            driveremployment__isnull=True
        ).select_related('tenant')
        
        if tenant_id:
            drivers_query = drivers_query.filter(tenant_id=tenant_id)
        
        drivers_without_employment = drivers_query.all()
        
        if not drivers_without_employment:
            self.stdout.write(
                self.style.SUCCESS('✅ All drivers have employment records!')
            )
            return
        
        self.stdout.write(
            self.style.WARNING(
                f'Found {len(drivers_without_employment)} drivers missing employment records:'
            )
        )
        
        # Show what will be done
        for driver in drivers_without_employment:
            # Determine what status would be set
            if driver.termination_date and driver.termination_date <= timezone.now().date():
                emp_status = EmploymentStatus.TERMINATED
                duty_status = DutyStatus.UNASSIGNED
                status_reason = "terminated"
            elif not driver.is_active:
                emp_status = EmploymentStatus.INACTIVE
                duty_status = DutyStatus.UNASSIGNED
                status_reason = "inactive"
            else:
                emp_status = EmploymentStatus.ACTIVE
                duty_status = DutyStatus.AVAILABLE
                status_reason = "active"
            
            self.stdout.write(
                f'  - {driver.first_name} {driver.last_name} (Tenant: {driver.tenant.name}) → {status_reason}'
            )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('🧪 DRY RUN - No changes made. Run without --dry-run to apply fixes.')
            )
            return
        
        # Confirm before proceeding
        confirm = input(f'\nCreate employment records for {len(drivers_without_employment)} drivers? [y/N]: ')
        if confirm.lower() != 'y':
            self.stdout.write(self.style.ERROR('❌ Operation cancelled.'))
            return
        
        # Create employment records
        created_count = 0
        error_count = 0
        
        with transaction.atomic():
            for driver in drivers_without_employment:
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
                        max_hours_per_week=40,
                    )
                    
                    created_count += 1
                    self.stdout.write(
                        f'✅ Created employment record for {driver.first_name} {driver.last_name}'
                    )
                    
                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'❌ Failed to create employment record for {driver.first_name} {driver.last_name}: {str(e)}'
                        )
                    )
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(
            self.style.SUCCESS(f'✅ Successfully created {created_count} employment records')
        )
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'❌ {error_count} errors occurred')
            )
        
        self.stdout.write(
            self.style.SUCCESS('🎉 Operation completed!')
        ) 