#!/usr/bin/env sh
# Pre-flight for the talk: run it ~10 minutes before going on stage.
#   1. Checks sign-in and that the demo state is the expected one.
#   2. Warms every hosted agent (cold starts are 7-13 s) and the A2A hop.
#   3. Fires the Act 3 question once, so its trace is already in the portal by Act 4.
# Usage: scripts/preflight.sh
set -u
cd "$(dirname "$0")/.."
ok() { printf '  OK    %s\n' "$1"; }
ko() { printf '  FAIL  %s\n' "$1"; FAILED=1; }
FAILED=0
q() { azd env get-value "$1" 2>/dev/null; }

echo "== Sign-in"
az account get-access-token --resource https://ai.azure.com --query expiresOn -o tsv >/dev/null 2>&1 && ok "az login" || ko "az login (run: az login)"
azd auth token >/dev/null 2>&1 && ok "azd auth" || ko "azd auth (run: azd auth login)"

echo "== Demo state"
[ -z "$(q AGENT_PROMPT)" ] && ok "hr-benefits-agent prompt is baseline (Act 2 changes it live)" || ko "AGENT_PROMPT is '$(q AGENT_PROMPT)': run azd env set AGENT_PROMPT \"\" && azd deploy hr-benefits-agent"
[ -z "$(q HR_AGENT_PROMPT)" ] && ok "hr-agent prompt is baseline" || ko "HR_AGENT_PROMPT is '$(q HR_AGENT_PROMPT)' (leaky?): set it to \"\" and redeploy hr-agent with the guardrail manifest"
git diff --quiet azure.yaml && ok "azure.yaml is the default manifest" || ko "azure.yaml is modified: git checkout azure.yaml"
SUB=$(q AZURE_SUBSCRIPTION_ID); RG=$(q AZURE_RESOURCE_GROUP); ACC=$(q AZURE_AI_ACCOUNT_NAME)
az rest --method get --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/$ACC/raiPolicies/hr-agent-guard?api-version=2025-06-01" --query name -o tsv >/dev/null 2>&1 \
  && ok "guardrail policy hr-agent-guard exists" || ko "guardrail policy hr-agent-guard is missing (fails open!)"

echo "== Warm-up (new sessions, so the stage demos start clean)"
for pair in "hr-benefits-agent|Tell me about the Remote Work benefit." \
            "it-agent|What laptop does a software engineer get?" \
            "hr-agent|I start Monday as a consultant: what do I need to do in my first week, and which accounts will I get?"; do
  agent=${pair%%|*}; question=${pair#*|}
  out="$(azd ai agent invoke "$agent" --new-session --no-prompt "$question" 2>&1)"
  trace="$(printf '%s\n' "$out" | sed -n 's/^Trace ID: *//p')"
  printf '%s\n' "$out" | grep -q "^\[$agent\]" && ok "$agent answered (trace $trace)" || { ko "$agent did not answer"; printf '%s\n' "$out" | tail -5; }
done

echo "== Guardrail"
probe="$(scripts/probe-guardrail.sh 2>&1)"
printf '%s\n' "$probe" | grep -q "jailbreak *BLOCKED" && ok "jailbreak BLOCKED at input stage" || ko "jailbreak NOT blocked: use the saved backup for Act 5"

echo
[ "$FAILED" -eq 0 ] && echo "All good. The hr-agent trace above is the one to open in Act 4." || echo "Something failed: see Part 2 of docs/demo-guide.md."
