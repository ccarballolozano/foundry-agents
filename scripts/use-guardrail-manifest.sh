#!/usr/bin/env sh
# Render azure-with-guardrail.yaml into azure.yaml, filling in the guardrail policy IDs
# from the azd environment.
#
# Why: azd does not expand ${VAR} inside a service's `policies:` block (it sends the literal
# text and the deploy fails with "RAI policy name must be a fully qualified ... ARM resource ID").
# Every other ${VAR} in the manifest (env:, endpoint:) is left for azd to expand as usual.
#
# Usage:
#   scripts/use-guardrail-manifest.sh      # azure.yaml now carries the guardrail
#   azd deploy hr-agent
#   git checkout azure.yaml                # back to the manifest without a guardrail
#
# The rendered azure.yaml contains real policy IDs: do not commit it.
set -eu

cd "$(dirname "$0")/.."

for var in HR_AGENT_RAI_POLICY_ID HR_BENEFITS_AGENT_RAI_POLICY_ID; do
  value="$(azd env get-value "$var" 2>/dev/null || true)"
  case "$value" in
    /subscriptions/*/providers/Microsoft.CognitiveServices/accounts/*/raiPolicies/*) ;;
    *) echo "$var is unset or is not a full raiPolicies ARM ID. See 'Apply Guardrails' in README.md." >&2; exit 1 ;;
  esac
  eval "$var=\$value"
done

sed -e "s#\${HR_AGENT_RAI_POLICY_ID}#$HR_AGENT_RAI_POLICY_ID#" \
    -e "s#\${HR_BENEFITS_AGENT_RAI_POLICY_ID}#$HR_BENEFITS_AGENT_RAI_POLICY_ID#" \
    azure-with-guardrail.yaml > azure.yaml

echo "azure.yaml now uses the guardrail policies from the azd environment (do not commit it)."
echo "Restore the default manifest with: git checkout azure.yaml"
