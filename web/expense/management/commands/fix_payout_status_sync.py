from django.core.management.base import BaseCommand
from django.utils import timezone
from expense.models import Payout, PayoutStatus
from tenant.models import Tenant


class Command(BaseCommand):
    help = 'Fix status synchronization issues across all completed payouts'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=int,
            help='Specific tenant ID to fix (optional)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Fix issues without prompting for confirmation'
        )

    def handle(self, *args, **options):
        tenant_id = options.get('tenant_id')
        dry_run = options.get('dry_run', False)
        force = options.get('force', False)
        
        self.stdout.write("=" * 70)
        self.stdout.write("PAYOUT STATUS SYNCHRONIZATION CHECKER/FIXER")
        self.stdout.write("=" * 70)
        
        # Get payouts to check
        if tenant_id:
            try:
                tenant = Tenant.objects.get(pk=tenant_id)
                payouts = Payout.objects.filter(
                    tenant=tenant,
                    status=PayoutStatus.COMPLETED
                ).order_by('-created_at')
                self.stdout.write(f"Checking payouts for tenant: {tenant}")
            except Tenant.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Tenant with ID {tenant_id} does not exist')
                )
                return
        else:
            payouts = Payout.objects.filter(
                status=PayoutStatus.COMPLETED
            ).order_by('-created_at')
            self.stdout.write("Checking all completed payouts across all tenants")
        
        total_payouts = payouts.count()
        self.stdout.write(f"Found {total_payouts} completed payouts to check\n")
        
        if total_payouts == 0:
            self.stdout.write("No completed payouts found.")
            return
        
        # Track results
        payouts_with_issues = 0
        total_issues_found = 0
        total_fixes_applied = 0
        
        for i, payout in enumerate(payouts, 1):
            self.stdout.write(f"[{i}/{total_payouts}] Checking payout {payout.pk} ({payout.driver})...")
            
            try:
                # Check for sync issues
                sync_result = payout.check_and_fix_expense_status_sync(
                    user=None, 
                    force_fix=False  # Just check first
                )
                
                if sync_result['has_issues']:
                    payouts_with_issues += 1
                    total_issues_found += len(sync_result['issues_found'])
                    
                    self.stdout.write(f"  ❌ Found {len(sync_result['issues_found'])} sync issues:")
                    for issue in sync_result['issues_found']:
                        self.stdout.write(f"    • {issue}")
                    
                    # Apply fixes if not dry run
                    if not dry_run:
                        if force or self._confirm_fix(payout):
                            fix_result = payout.check_and_fix_expense_status_sync(
                                user=None,
                                force_fix=True  # Actually fix
                            )
                            
                            fixes_applied = len(fix_result['fixes_applied'])
                            total_fixes_applied += fixes_applied
                            
                            if fixes_applied > 0:
                                self.stdout.write(f"  ✅ Applied {fixes_applied} fixes:")
                                for fix in fix_result['fixes_applied']:
                                    self.stdout.write(f"    • {fix}")
                            else:
                                self.stdout.write("  ⚠️ No fixes could be applied")
                        else:
                            self.stdout.write("  ⏭️ Skipped (user choice)")
                    else:
                        self.stdout.write("  ⏭️ Skipped (dry run mode)")
                        
                else:
                    self.stdout.write(f"  ✅ No sync issues found")
                    
            except Exception as e:
                self.stdout.write(f"  ❌ Error checking payout: {str(e)}")
        
        # Summary
        self.stdout.write("\n" + "=" * 70)
        self.stdout.write("SUMMARY")
        self.stdout.write("=" * 70)
        self.stdout.write(f"Total payouts checked: {total_payouts}")
        self.stdout.write(f"Payouts with sync issues: {payouts_with_issues}")
        self.stdout.write(f"Total issues found: {total_issues_found}")
        
        if dry_run:
            self.stdout.write(f"Fixes that would be applied: {total_issues_found}")
            self.stdout.write("\nRun without --dry-run to actually apply fixes.")
        else:
            self.stdout.write(f"Fixes applied: {total_fixes_applied}")
            remaining_issues = total_issues_found - total_fixes_applied
            if remaining_issues > 0:
                self.stdout.write(f"Issues remaining: {remaining_issues}")
        
        self.stdout.write("=" * 70)
    
    def _confirm_fix(self, payout):
        """Ask user for confirmation before fixing a specific payout"""
        response = input(f"Fix sync issues for payout {payout.pk} ({payout.driver})? [y/N]: ").lower()
        return response in ['y', 'yes'] 