# Expense System Status Workflow Documentation

## Overview

The expense system uses multiple status types to track different aspects of expense management and payment workflows. This document explains each status type, their meanings, and workflows.

## Status Types

### 1. AccountPayableStatus (BVD & OtherExpense)

Controls the accounting and payment workflow for expenses.

**Statuses:**
- **PENDING**: Expense recorded but not yet reviewed/approved
  - Initial status for all new expenses
  - Expenses can be edited/deleted
  - Not included in payout calculations

- **ACCOUNTED**: Expense reviewed and approved for inclusion in payouts
  - Finance/Admin has reviewed and approved the expense
  - Expense is locked from editing
  - Included in payout calculations
  - Ready for payment processing

- **PAID**: Expense has been paid to driver (included in completed payout)
  - Automatically set when payout is marked as COMPLETED
  - Final status - no further changes allowed
  - Audit trail for payment confirmation

**Workflow Transitions:**
```
PENDING → ACCOUNTED → PAID
```

### 2. ReimbursementStatus (OtherExpense only)

Tracks driver reimbursement approval workflow for out-of-pocket expenses.

**Statuses:**
- **PENDING**: Awaiting approval from supervisor/admin
- **APPROVED**: Approved for reimbursement, ready for payment
- **REJECTED**: Rejected, not eligible for reimbursement (can be re-submitted)
- **PAID**: Reimbursement paid to driver

**Workflow Transitions:**
```
PENDING → APPROVED → PAID
PENDING → REJECTED → PENDING (can be resubmitted)
APPROVED → REJECTED (if later found invalid)
```

### 3. PayoutStatus

Controls the monthly payout processing workflow.

**Statuses:**
- **DRAFT**: Calculation done, not yet finalized
  - Initial status after payout calculation
  - Can be recalculated
  - Expenses can still be modified

- **PROCESSING**: Being processed for payment
  - Payout locked from recalculation
  - Payment processing initiated
  - Related expenses should not be modified

- **COMPLETED**: Payment completed and invoices generated
  - Final status
  - Automatically marks related expenses as PAID
  - Creates audit trail for completed payment

- **CANCELLED**: Payout cancelled
  - Can be reactivated to DRAFT if needed
  - Related expenses return to previous status

**Workflow Transitions:**
```
DRAFT → PROCESSING → COMPLETED
DRAFT → CANCELLED → DRAFT (reactivation)
PROCESSING → CANCELLED → DRAFT (if payment fails)
```

## Business Rules

### Expense Inclusion in Payouts

Only expenses with the following status combinations are included in payout calculations:

**BVD Expenses:**
- AccountPayableStatus: PENDING or ACCOUNTED

**Other Expenses:**
- AccountPayableStatus: PENDING or ACCOUNTED
- ReimbursementStatus: APPROVED (for reimbursable expenses)

### Automatic Status Changes

**When Payout is marked COMPLETED:**
- All related BVD expenses: PENDING/ACCOUNTED → PAID
- All related Other expenses: PENDING/ACCOUNTED → PAID  
- Other expenses with PENDING/APPROVED reimbursement: → PAID

**Important Notes:**
- Expenses included in payout calculations (both PENDING and ACCOUNTED) are automatically marked as PAID when the payout is completed
- This reflects the business reality that payment has been processed for all expenses in the payout
- The system uses automatic transitions that bypass normal user workflow restrictions
- All status changes are logged with audit trails indicating system-initiated changes

### Status Validation

- Status transitions are validated using workflow rules
- Invalid transitions are rejected with error messages
- Audit logging tracks all status changes with user information

## User Permissions

### Finance/Admin Users:
- Can change AccountPayableStatus (PENDING → ACCOUNTED)
- Can manage PayoutStatus transitions
- Can approve/reject reimbursement requests

### Drivers:
- Can submit expenses (creates PENDING status)
- Can view their expense and payout status
- Cannot modify status after submission

### Supervisors:
- Can approve/reject reimbursement requests
- Can view team expense reports

## UI Implementation

### Status Badges
- Consistent color coding across all templates
- Dynamic badge colors based on status type
- Icons and hover tooltips for status meanings

### Status Transitions
- Dropdown menus showing only valid next statuses
- AJAX-enabled status updates
- Confirmation dialogs for irreversible changes

### Filtering and Reporting
- Status-based filtering in all list views
- Status transition history tracking
- Export functionality includes status information

## API Endpoints

### Status Transition
```
POST /expense/status/<model_type>/<pk>/
Parameters:
- new_status: Target status value
- status_type: 'status' or 'reimbursement_status'
```

### Status Options
```
GET /expense/status-options/<model_type>/<pk>/
Parameters:
- status_type: 'status' or 'reimbursement_status'
Returns: Available transition options
```

## Error Handling

### Validation Errors
- Clear error messages for invalid status transitions
- User-friendly explanations of workflow requirements
- Suggestions for corrective actions

### Business Rule Violations
- Prevents modification of locked records
- Warns users about impact of status changes
- Provides rollback options where appropriate

## Maintenance

### Database Migrations
- Status enum changes require careful migration planning
- Existing data validation during migrations
- Backward compatibility considerations

### Monitoring
- Status transition logging for audit trails
- Performance monitoring for bulk status updates
- Regular cleanup of stale draft payouts 