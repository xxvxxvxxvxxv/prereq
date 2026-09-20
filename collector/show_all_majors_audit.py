import json, collections
from pathlib import Path

p = Path("collector/output/all-majors-audit.json")
d = json.loads(p.read_text(encoding="utf-8"))

print("PROGRAMS")
for code,row in d.get("programs",{}).items():
    print(f"{code:10} courses={row['unique']:3} parsed={row['parsed']:3} none={row['noPrerequisite']:3} unknown={row['unknown']:3}")

print("\nUNKNOWN RULES:", len(d.get("unknownRules",[])))
for x in d.get("unknownRules",[]):
    print(" ", x)

print("\nRULE CONFLICTS:", len(d.get("ruleConflicts",[])))
for x in d.get("ruleConflicts",[]):
    print(" ", x)

changes = d.get("legacyChanges",[])
uniq = sorted(set(x["course"] for x in changes))
print("\nLEGACY RULES REFRESHED:", len(changes), "events /", len(uniq), "unique courses")
print(" ", ", ".join(uniq))

errors=d.get("errors",[])
targets=collections.Counter(x.get("course","DEGREE:"+x.get("program","?")) for x in errors)
print("\nERRORS:",len(errors),"events /",len(targets),"unique targets")
for k,v in targets.items():
    print(" ",k,"x",v)
