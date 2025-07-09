"""
Management command to check and fix dispatch system health.

Usage:
    python manage.py check_dispatch_health --tenant-id=<id>
    python manage.py check_dispatch_health --all-tenants
    python manage.py check_dispatch_health --fix --dry-run=false
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from tenant.models import Tenant
from dispatch.utils import detect_status_inconsistencies, fix_status_inconsistencies
import json
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Check and fix dispatch system health issues'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant-id',
            type=str,
            help='Check specific tenant by ID'
        )
        
        parser.add_argument(
            '--all-tenants',
            action='store_true',
            help='Check all tenants'
        )
        
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Attempt to fix detected issues'
        )
        
        parser.add_argument(
            '--dry-run',
            type=str,
            default='true',
            choices=['true', 'false'],
            help='Run in dry-run mode (default: true)'
        )
        
        parser.add_argument(
            '--output-format',
            type=str,
            default='summary',
            choices=['summary', 'detailed', 'json'],
            help='Output format (default: summary)'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run'].lower() == 'true'
        
        # Determine which tenants to check
        tenants = []
        if options['tenant_id']:
            try:
                tenant = Tenant.objects.get(id=options['tenant_id'])
                tenants = [tenant]
            except Tenant.DoesNotExist:
                raise CommandError(f"Tenant with ID {options['tenant_id']} not found")
        elif options['all_tenants']:
            tenants = Tenant.objects.filter(is_active=True)
        else:
            raise CommandError("Must specify either --tenant-id or --all-tenants")

        if not tenants:
            self.stdout.write(self.style.WARNING('No tenants found to check'))
            return

        overall_results = {
            'tenants_checked': len(tenants),
            'total_issues': 0,
            'critical_issues': 0,
            'fixes_applied': 0,
            'tenant_results': []
        }

        for tenant in tenants:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Checking tenant: {tenant.name} (ID: {tenant.id})")
            self.stdout.write(f"{'='*60}")

            try:
                # Detect inconsistencies
                inconsistencies = detect_status_inconsistencies(tenant)
                
                if 'error' in inconsistencies:
                    self.stdout.write(
                        self.style.ERROR(f"Error detecting issues: {inconsistencies['error']}")
                    )
                    continue

                total_issues = inconsistencies['summary']['total_issues']
                critical_issues = inconsistencies['summary']['critical_issues']
                
                overall_results['total_issues'] += total_issues
                overall_results['critical_issues'] += critical_issues

                # Display results
                if total_issues == 0:
                    self.stdout.write(
                        self.style.SUCCESS("✅ No issues detected! Dispatch system is healthy.")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"⚠️  Found {total_issues} issues ({critical_issues} critical)")
                    )
                    
                    if options['output_format'] in ['detailed', 'json']:
                        self._display_detailed_issues(inconsistencies, options['output_format'])
                    else:
                        self._display_summary_issues(inconsistencies)

                # Apply fixes if requested
                if options['fix'] and total_issues > 0:
                    self.stdout.write(f"\n🔧 Attempting to fix issues...")
                    if dry_run:
                        self.stdout.write(self.style.WARNING("Running in DRY-RUN mode - no changes will be made"))
                    
                    fix_results = fix_status_inconsistencies(tenant, inconsistencies, dry_run)
                    
                    if 'error' in fix_results:
                        self.stdout.write(
                            self.style.ERROR(f"Error fixing issues: {fix_results['error']}")
                        )
                    else:
                        fixes_applied = fix_results['summary']['successful_fixes']
                        fixes_failed = fix_results['summary']['failed_fixes']
                        overall_results['fixes_applied'] += fixes_applied
                        
                        if fixes_applied > 0:
                            self.stdout.write(
                                self.style.SUCCESS(f"✅ Successfully applied {fixes_applied} fixes")
                            )
                        if fixes_failed > 0:
                            self.stdout.write(
                                self.style.ERROR(f"❌ {fixes_failed} fixes failed")
                            )
                        
                        if options['output_format'] == 'detailed':
                            self._display_fix_details(fix_results)

                # Store tenant results
                tenant_result = {
                    'tenant_id': str(tenant.id),
                    'tenant_name': tenant.name,
                    'issues_found': total_issues,
                    'critical_issues': critical_issues,
                    'inconsistencies': inconsistencies if options['output_format'] == 'json' else None
                }
                
                if options['fix']:
                    tenant_result['fixes_applied'] = fix_results['summary']['successful_fixes']
                    tenant_result['fixes_failed'] = fix_results['summary']['failed_fixes']
                
                overall_results['tenant_results'].append(tenant_result)

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Unexpected error checking tenant {tenant.name}: {str(e)}")
                )
                logger.exception(f"Error checking tenant {tenant.id}")

        # Display overall summary
        self._display_overall_summary(overall_results, options)

    def _display_summary_issues(self, inconsistencies):
        """Display a summary of issues found"""
        if inconsistencies['dispatch_order_mismatches']:
            count = len(inconsistencies['dispatch_order_mismatches'])
            self.stdout.write(f"  • {count} dispatch-order status mismatches")
        
        if inconsistencies['dispatch_trip_mismatches']:
            count = len(inconsistencies['dispatch_trip_mismatches'])
            self.stdout.write(f"  • {count} dispatch-trip status mismatches")
        
        if inconsistencies['assignment_resource_mismatches']:
            count = len(inconsistencies['assignment_resource_mismatches'])
            self.stdout.write(f"  • {count} assignment-resource status mismatches")
        
        if inconsistencies['orphaned_assignments']:
            count = len(inconsistencies['orphaned_assignments'])
            self.stdout.write(f"  • {count} orphaned assignments")
        
        if inconsistencies['resource_conflicts']:
            count = len(inconsistencies['resource_conflicts'])
            self.stdout.write(
                self.style.ERROR(f"  • {count} CRITICAL resource conflicts")
            )

    def _display_detailed_issues(self, inconsistencies, output_format):
        """Display detailed issues"""
        if output_format == 'json':
            self.stdout.write(json.dumps(inconsistencies, indent=2))
        else:
            # Display detailed breakdown
            for category, issues in inconsistencies.items():
                if category == 'summary' or not issues:
                    continue
                
                self.stdout.write(f"\n{category.replace('_', ' ').title()}:")
                for issue in issues[:5]:  # Limit to first 5 items
                    self.stdout.write(f"  - {json.dumps(issue, indent=4)}")
                
                if len(issues) > 5:
                    self.stdout.write(f"  ... and {len(issues) - 5} more")

    def _display_fix_details(self, fix_results):
        """Display details of fixes applied"""
        self.stdout.write("\nFix Details:")
        
        for fix in fix_results['fixes_applied']:
            self.stdout.write(f"  ✅ {fix['type']}: {fix['action']}")
        
        for fix in fix_results['fixes_failed']:
            self.stdout.write(f"  ❌ {fix['type']}: {fix['error']}")

    def _display_overall_summary(self, results, options):
        """Display overall summary across all tenants"""
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write("OVERALL SUMMARY")
        self.stdout.write(f"{'='*60}")
        
        self.stdout.write(f"Tenants checked: {results['tenants_checked']}")
        self.stdout.write(f"Total issues found: {results['total_issues']}")
        self.stdout.write(f"Critical issues: {results['critical_issues']}")
        
        if options['fix']:
            self.stdout.write(f"Fixes applied: {results['fixes_applied']}")
        
        if results['total_issues'] == 0:
            self.stdout.write(
                self.style.SUCCESS("\n🎉 All dispatch systems are healthy!")
            )
        elif results['critical_issues'] > 0:
            self.stdout.write(
                self.style.ERROR(f"\n⚠️  ATTENTION: {results['critical_issues']} critical issues require immediate attention")
            )
        
        if options['output_format'] == 'json':
            self.stdout.write(f"\nFull Results JSON:")
            self.stdout.write(json.dumps(results, indent=2)) 