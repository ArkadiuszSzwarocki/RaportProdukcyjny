# Attendance and report release
<!-- cspell:words Inno -->

Attendance submissions are serialized per employee and duplicate assignments
do not create additional history. Leave approval updates the request, attendance
and leave counters in one transaction. Repeated approval is a no-op.

Reports use the latest roster assignment on or before the report date; a missing
assignment during sickness does not remove an AGRO employee from the report.
Approved leave requests and their generated attendance records are merged once.
Manual report emails require a valid PDF attachment and use application/pdf MIME.

## Automatic reports

ENABLE_AUTO_REPORT_SCHEDULER defaults to false in every application copy,
including the normal hardware-daemon service. This leaves pallet automation
enabled while preventing local applications from reserving report attempts.
The production QNAP runs a separate report process. Updating a local checkout
must be followed by restarting that application for the disabled timer to apply.

Update the separate report process to the same validated image as the main
application when releasing this package. Do not enable an additional embedded
timer. Keep the existing report advisory locks until every legacy application
has been updated and restarted. Preserve postponement, pause, exact scheduled
minute and durable single-attempt history; never reset failed reports to retry.

Historical duplicate attendance rows require a reviewed correction. This release
does not delete production history or change production schemas. Transactional
attendance tables must use InnoDB before deploying the locking changes.
