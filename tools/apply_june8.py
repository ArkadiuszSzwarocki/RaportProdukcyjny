"""
Selectively apply files from the June 8 22:28 commit, skipping Zasyp/Workowanie protected files.
"""
import subprocess

# Files/patterns to NEVER touch (Zasyp/Workowanie AGRO core)
PROTECTED = [
    "templates/dashboard.html",
    "templates/includes/dashboard_plan_loop.html",
    "templates/dashboard/_dashboard_agro_active.html",
    "templates/dashboard/_dashboard_agro_active_details.html",
    "templates/dashboard/_dashboard_agro_stages.html",
    "templates/dashboard/_dashboard_agro_top_bar.html",
    "templates/dashboard/_dashboard_order_card.html",
    "templates/dashboard/_dashboard_production_list.html",
    "templates/dashboard/_dashboard_agro_machine_stats.html",
    "templates/dashboard/_dashboard_agro_settlement.html",
    "templates/dashboard/_dashboard_banners.html",
    "templates/dashboard/_dashboard_init.html",
    "templates/dashboard/_dashboard_planner_alerts.html",
    # Don't touch the main production blueprint (zasyp_flow, zasyp_etapy, orders)
    "app/blueprints/production/zasyp_flow.py",
    "app/blueprints/production/zasyp_etapy.py",
    "app/blueprints/production/orders.py",
    # Don't touch dashboard context/service (workowanie logic)
    "app/services/dashboard_context_service.py",
    "app/services/dashboard_service.py",
    "app/core/contexts.py",
    # Don't touch etapy.js (already patched manually)
    "static/js/dashboard/etapy.js",
    # Don't touch the main plan loop
    "templates/includes/dashboard_footer.html",
    "templates/includes/dashboard_plan_loop.html",
    "templates/dashboard_global.html",
]

def is_protected(filepath):
    for p in PROTECTED:
        if filepath == p or filepath.startswith(p.rstrip("/")):
            return True
    return False

COMMIT = "876ed1e44383f1013a53ba0f6f787239c4089269"

def get_files_in_commit(commit_hash):
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
        capture_output=True, text=True, cwd="a:/GitHub/RaportProdukcyjny"
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]

def checkout_file_from_commit(commit_hash, filepath):
    result = subprocess.run(
        ["git", "checkout", commit_hash, "--", filepath],
        capture_output=True, text=True, cwd="a:/GitHub/RaportProdukcyjny"
    )
    return result.returncode, result.stderr

print(f"=== Applying commit {COMMIT[:8]} (8 June 22:28) selectively ===\n")
applied = []
skipped = []
errors = []

files = get_files_in_commit(COMMIT)
for filepath in files:
    if is_protected(filepath):
        print(f"  [PROTECTED] {filepath}")
        skipped.append(filepath)
    else:
        rc, err = checkout_file_from_commit(COMMIT, filepath)
        if rc == 0:
            print(f"  [OK] {filepath}")
            applied.append(filepath)
        else:
            print(f"  [ERROR] {filepath}: {err.strip()}")
            errors.append((filepath, err.strip()))

print(f"\n=== DONE ===")
print(f"Applied: {len(applied)} files")
print(f"Skipped (protected): {len(skipped)} files")
print(f"Errors: {len(errors)} files")
if errors:
    print("\nErrors:")
    for f, e in errors:
        print(f"  {f}: {e}")
