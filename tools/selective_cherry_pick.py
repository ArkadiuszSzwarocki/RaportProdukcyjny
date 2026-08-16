"""
Selectively apply files from commits, skipping files that touch Zasyp/Workowanie AGRO templates.
"""
import subprocess
import sys

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

# Commits from oldest to newest (June 1 -> June 3)
# Exclude d19d95e (merge commit, empty) and f242d9 (popup only - partially OK)
COMMITS = [
    "f242d919a2af8d8e52fa446d756d5d155a9e9cbd",  # popup sizing (css + scripts + login) 2026-06-01 00:13
    "fb4ed57cea9d1bc56e41dfe48da02b851f5630c8",  # printer bridge fix 2026-06-01 09:56
    "be4c2e65147c8e939f31d89f6dfec4bc14023e3b",  # guard sidebar links 2026-06-01 10:02
    "e30d9505841615c8b2d6cfd6824131c35be1daaa",  # guard AGRO surowce link 2026-06-01 10:05
    "37d830b56492bdc0563b61b9c1539ae787a643fc",  # guard warehouse split link 2026-06-01 10:09
    "4a6cf0f04b8ec7c34a4266be0798a0a630cc5db9",  # AGRO pallet numbering fix 2026-06-01 10:20 - PROTECTED!
    "4b838711737917e9ab3f8dfc3cb6a64ef4bd7991",  # label bridge autostart 2026-06-01 16:28
    "f696955e72714193c4b5fa069023df4cb1006592",  # flask-cors fix 2026-06-01 16:46
    "3c321f47cec749b88233761eaf69ee2861135818",  # TCP retry 2026-06-01 16:58
    "319b0d6553b36b0cbebdbd8f90d3679def425c05",  # Fallback active printers 2026-06-01 17:05
    "dc93e52eeb3dec894198892189bd065c4019207b",  # increase TCP timeout 2026-06-01 17:09
    "983c6f757f3b8905400fe1e18d3da4e9241822c0",  # align bridge timeout 2026-06-01 17:13
    "72249631bad62a7738ee1e187e2d24b5aa2a9d0b",  # local-bridge fallback 2026-06-01 17:26
    "d55a4369fdd4d8f4239684889977ac34b5816a22",  # shared bridge fallback 2026-06-01 17:32
    "f8ed760dee60d1468e722a2f507b3c2d2e8916ad",  # magazyny_nowe print flow 2026-06-01 17:43
    "7c0e50fd82d32e5e05e4150358264e116a525e7f",  # fix silent print click 2026-06-01 17:51
    "18b715b9990072077c6255744fe50726655bffc3",  # HTTP/HTTPS bridge fallback 2026-06-01 17:59
    "cce1d8e58042af3caa1d031cb9bb40b71f96b7b8",  # enhance packaging return 2026-06-01 22:34
    "bfa1db3afd27651fd132c750a8703fb5cd5e8e02",  # fix duplicated magazyn_dostawy 2026-06-02 19:54
    "342c64269603162fb9d1459638af905c46863bfd",  # QR code scanner 2026-06-02 20:13
    "194ddd44eb3059f5378215a0d0b53cbb68c40296",  # inventory tools 2026-06-03 00:25
]

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

print("=== Selective cherry-pick started ===\n")
applied = []
skipped = []
errors = []

for commit in COMMITS:
    files = get_files_in_commit(commit)
    if not files:
        print(f"[SKIP] {commit[:8]} - merge commit or empty")
        continue
    
    print(f"\n[COMMIT] {commit[:8]}")
    for filepath in files:
        if is_protected(filepath):
            print(f"  [PROTECTED] {filepath}")
            skipped.append((commit[:8], filepath))
        else:
            rc, err = checkout_file_from_commit(commit, filepath)
            if rc == 0:
                print(f"  [OK] {filepath}")
                applied.append((commit[:8], filepath))
            else:
                print(f"  [ERROR] {filepath}: {err.strip()}")
                errors.append((commit[:8], filepath, err.strip()))

print(f"\n\n=== DONE ===")
print(f"Applied: {len(applied)} files")
print(f"Skipped (protected): {len(skipped)} files")
print(f"Errors: {len(errors)} files")
if errors:
    print("\nErrors:")
    for c, f, e in errors:
        print(f"  {c} {f}: {e}")
