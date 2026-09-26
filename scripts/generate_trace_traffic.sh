#!/usr/bin/env bash
set -euo pipefail

# Genera tráfico deliberado para tener varias ejecuciones interesantes en
# Foundry Trace/Monitor. Ejecutar desde la raíz del proyecto.
#
# Requisitos:
#   - azd autenticado
#   - agente desplegado y activo
#
# Uso:
#   chmod +x scripts/generate_trace_traffic.sh
#   ./scripts/generate_trace_traffic.sh
#
# Mientras corre, en otra terminal puedes usar:
#   azd ai agent monitor --follow

invoke() {
  local label="$1"
  local prompt="$2"

  echo
  echo "============================================================"
  echo "[$label]"
  echo "$prompt"
  echo "============================================================"

  azd ai agent invoke "$prompt"
}

# ---------------------------------------------------------------------------
# 1. Consultas sencillas: respuestas que deberían requerir la tool.
# ---------------------------------------------------------------------------
invoke "01 - Learning Budget" \
  "Tell me about the Learning Budget benefit and who is eligible."

invoke "02 - Remote Work" \
  "What is the Remote Work benefit and who can use it?"

invoke "03 - Health Insurance" \
  "What does Health Insurance cover and who is eligible?"

# ---------------------------------------------------------------------------
# 2. Caso que fuerza al agente a reconocer que no existe el beneficio.
# ---------------------------------------------------------------------------
invoke "04 - Unsupported benefit" \
  "Do we offer a Childcare Benefit? If not, tell me which benefits are available."

# ---------------------------------------------------------------------------
# 3. Consulta que mezcla dos beneficios: útil para ver más de una interacción
#    de tool / razonamiento en una misma ejecución.
# ---------------------------------------------------------------------------
invoke "05 - Cross-benefit comparison" \
  "Compare the eligibility requirements for Remote Work and the Learning Budget."

# ---------------------------------------------------------------------------
# 4. Caso con información insuficiente / frontera de conocimiento.
# ---------------------------------------------------------------------------
invoke "06 - Unsupported specific policy detail" \
  "Can you tell me the exact reimbursement amount for the Learning Budget?"

# ---------------------------------------------------------------------------
# 5. Multiturno: azd reutiliza por defecto la sesión de la última invocación.
#    Estas dos llamadas se plantean como una conversación encadenada.
# ---------------------------------------------------------------------------
invoke "07 - Conversation turn 1" \
  "I am most interested in the Learning Budget. Summarize its eligibility in one sentence."

invoke "08 - Conversation turn 2" \
  "Now compare that benefit with Remote Work, focusing only on eligibility."

# ---------------------------------------------------------------------------
# 6. Nueva sesión: mismo tipo de pregunta, pero sin depender de la sesión
#    anterior. Esto nos permite contrastar la continuidad.
# ---------------------------------------------------------------------------
echo
echo "============================================================"
echo "[09 - New session]"
echo "What benefit was I just asking about?"
echo "============================================================"

azd ai agent invoke --new-session \
  "What benefit was I just asking about?"

echo
echo "============================================================"
echo "Traffic generation finished."
echo "============================================================"
echo
echo "Para investigar una ejecución concreta:"
echo "  1. Anota el session ID que muestra azd ai agent invoke."
echo "  2. Usa: azd ai agent monitor --session-id <SESSION_ID> --follow"
echo
echo "Para ver trazas en Foundry, espera unos minutos y abre Trace/Trajectories."
