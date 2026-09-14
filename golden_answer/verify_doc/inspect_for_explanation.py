import inspect, os, sys

# Resolve the package root from this file's own location so the helper keeps
# working after the project is moved/extracted anywhere:
#   <project>/golden_answer/verify_doc/inspect_for_explanation.py
#   -> <project>/golden_answer
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from app import repository, service, state_machine

print("== app/state_machine.py: AFTER_SALE_TRANSITIONS ==")
for source, targets in state_machine.AFTER_SALE_TRANSITIONS.items():
    print(f"  {source:<14} -> {sorted(targets) or 'TERMINAL'}")
print()
print("== app/state_machine.py: REFUND_START_STATES ==")
print(" ", sorted(state_machine.REFUND_START_STATES))
print()
print("== app/service.py: quota guard actually executed in _claim_refund ==")
src = inspect.getsource(service._claim_refund)
for line in src.splitlines():
    if "reserve_refund_quota" in line or "can_start_refund" in line or "insert_refund" in line or "update_after_sale_status" in line:
        print("  " + line.strip())
print()
print("== app/repository.py: reserve_refund_quota SQL guard ==")
src = inspect.getsource(repository.reserve_refund_quota)
for line in src.splitlines():
    if "WHERE" in line or "refunded_amount + ? <=" in line or "payment_status" in line:
        print("  " + line.strip())
print()
print("== app/repository.py: partial unique index on successful refunds ==")
for line in repository.SCHEMA.splitlines():
    if "ux_refunds_one_success" in line or "ux_after_sales_idempotency" in line:
        print("  " + line.strip())
print()
print("== app/repository.py: write_tx isolation level ==")
src = inspect.getsource(repository.write_tx)
for line in src.splitlines():
    if "BEGIN" in line and not line.strip().startswith("#"):
        print("  " + line.strip())
print()
print("== app/service.py: release_refund_quota on provider failure ==")
src = inspect.getsource(service._settle)
for line in src.splitlines():
    if "release_refund_quota" in line or "result.ok" in line:
        print("  " + line.strip())
