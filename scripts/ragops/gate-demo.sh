#!/usr/bin/env bash
# F2/F4: show that changing a threshold changes the gate's outcome WITHOUT rebuilding the image.
#   scripts/ragops/gate-demo.sh <failing-result-file-on-the-results-volume> [passing-result-file]
# 1. re-apply the gate to an existing failing result (MODE=gate, seconds, no suite run): the Job fails
# 2. relax two thresholds in the ConfigMap ragops-gate (recall5_drop and faithfulness_min)
# 3. delete and re-apply the SAME Job manifest: it passes; the image printed is identical both times
# 4. restore the ConfigMap to the committed values (k8s/base/ragops-gate.yaml)
set -uo pipefail
here=$(cd "$(dirname "$0")/../.." && pwd); NS=${NS:-rahbar}
failing=${1:?usage: gate-demo.sh /results/<failing result>.json}
image() { kubectl get job eval -n "$NS" -o jsonpath='{.spec.template.spec.containers[0].image}'; }
rules() { kubectl get cm ragops-gate -n "$NS" -o jsonpath='{.data.gate\.yaml}' | grep -E "id: (recall5_drop|faithfulness_min)" | sed 's/^ *- //' | cut -c1-120; }
run() { "$here/scripts/ragops/eval.sh" gate gate-demo --candidate "$failing" --baseline /results/baselines/live.json; echo "job exit code: $?"; kubectl get job eval -n "$NS" --no-headers; echo "image: $(image)"; }
echo "### 1. thresholds as committed"; rules
echo; echo "### 2. gate Job on $(basename "$failing")"; run
echo; echo "### 3. edit the ConfigMap (no image rebuild): allow a 0.25 recall@5 drop and a 0.80 faithfulness floor"
kubectl get cm ragops-gate -n "$NS" -o jsonpath='{.data.gate\.yaml}' > /tmp/gate-demo.yaml
python3 - <<'PY'
import re
s = open("/tmp/gate-demo.yaml").read()
s = re.sub(r"(id: recall5_drop.*?value: )0\.02", r"\g<1>0.25", s)
s = re.sub(r"(id: faithfulness_min.*?value: )0\.89", r"\g<1>0.80", s)
open("/tmp/gate-demo.yaml", "w").write(s)
PY
kubectl create cm ragops-gate -n "$NS" --from-file=gate.yaml=/tmp/gate-demo.yaml --dry-run=client -o yaml | kubectl apply -f - >/dev/null
rules
echo; echo "### 4. the same Job manifest again"; run
echo; echo "### 5. restore the committed thresholds"; kubectl apply -f "$here/k8s/base/ragops-gate.yaml" >/dev/null; rules
