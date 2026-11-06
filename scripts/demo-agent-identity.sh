#!/usr/bin/env sh
# Demo: why a hosted agent having its OWN identity matters.
#
#   1. Show who hr-agent is (its identity) and exactly what that identity may do.
#   2. A user's token is refused by the hosted toolbox: only the agent's own identity is accepted.
#   3. Take the agent's one role away: the hosted agent can no longer read the handbook. Give it back: it can.
#
# Needs: az login, azd environment selected, hr-agent deployed, and the right to assign roles
# on the search service (Owner / User Access Administrator, for example through PIM).
# Usage: scripts/demo-agent-identity.sh
set -eu
cd "$(dirname "$0")/.."

PRINCIPAL="$(azd env get-value AGENT_HR_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID 2>/dev/null)"
SEARCH="$(azd env get-value HR_AGENT_SEARCH_SERVICE 2>/dev/null)"
RG="$(azd env get-value AZURE_RESOURCE_GROUP 2>/dev/null)"
SCOPE="$(az search service show -g "$RG" -n "$SEARCH" --query id -o tsv)"
ROLE="Search Index Data Reader"
QUESTION="How many weeks of parental leave does the second parent get?"

ask() {
  azd ai agent invoke hr-agent "$QUESTION" --new-session --no-prompt 2>&1 |
    grep -E "^\[hr-agent\]|ERROR" | cut -c1-230 || true
}

echo "== 1. Who is hr-agent, and what may it do?"
echo "   identity (object id): $PRINCIPAL"
az role assignment list --assignee "$PRINCIPAL" --all --query "[].{role:roleDefinitionName, scope:scope}" -o table 2>/dev/null |
  sed -e "s#/subscriptions/[^/]*/resourceGroups/[^/]*/providers/##"
echo "   -> one read-only role on the search service. No keys, no write access, no other resources."

echo
echo "== 2. A user token is refused by the hosted toolbox"
echo "   (local run pointed at hr-agent-toolbox: it signs in as YOU, not as the agent)"
HR_AGENT_DEV_TOOLBOX=hr-agent-toolbox .venv/bin/python agents/hr-agent/local.py "$QUESTION" 2>&1 |
  grep -E "AgenticIdentityToken|Could not connect" | head -2 | cut -c1-260 || true

echo
echo "== 3a. With the role: the hosted agent answers from the handbook"
ask

echo
echo "== 3b. Revoke the agent's role"
az role assignment delete --assignee "$PRINCIPAL" --role "$ROLE" --scope "$SCOPE"
echo "   role removed; waiting up to 5 minutes for the change to take effect..."
i=0
while [ "$i" -lt 10 ]; do
  out="$(ask)"
  case "$out" in *"16 weeks"*) i=$((i + 1)); sleep 30 ;; *) break ;; esac
done
echo "$out"

echo
echo "== 3c. Give it back"
az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role "$ROLE" --scope "$SCOPE" --query roleDefinitionName -o tsv
i=0
while [ "$i" -lt 10 ]; do
  out="$(ask)"
  case "$out" in *"16 weeks"*) break ;; *) i=$((i + 1)); sleep 30 ;; esac
done
echo "$out"
