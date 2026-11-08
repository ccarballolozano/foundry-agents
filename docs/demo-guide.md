# Demo guide: from a working agent to an operable one

This guide goes with the talk *Cómo pasar de un agente que funciona a un agente en producción y operable con Microsoft Foundry* (50 min, in Spanish). It explains each demo, lists the commands in order and says what you should see. Everything in it was run against a real Foundry project on 2026-11-07.

Pick the part you need:

- **You want to run it yourself.** Do [Part 1](#part-1-set-up-once), then [Part 2](#part-2-before-you-run-the-demo) and [Part 3](#part-3-the-demo-act-by-act).
- **You want to understand what's going on.** Read [The story](#the-story) and the *What it shows* notes in [Part 3](#part-3-the-demo-act-by-act). Each act links to the README section with the details.
- **You're giving the talk.** Run [Part 2](#part-2-before-you-run-the-demo), follow [Part 3](#part-3-the-demo-act-by-act), and keep [Part 5](#part-5-giving-the-talk) open for the timeline and fallbacks.

The slides are [`docs/talk/presentation.html`](talk/presentation.html), in Spanish: open it in a browser, no build or server needed. Arrow keys or a click advance. Keys `1`–`5` jump to an act (`0` the cover, `6` the closing), and a control bar with the same sections appears when the pointer reaches the bottom edge or when you press `M`; moving the mouse anywhere else never shows it. `N` opens the notes: a short explanation of the slide with links to its sources on Microsoft Learn and in this repository. `O` opens the index, `F` full screen, `R` replays a slide's animation and `Q` shows a full-screen QR code of the repository at any moment (it is also on the first and the last two slides). The demo slides replay each command and its real output, so the talk can be followed without Azure.

The QR code is an SVG path inside the file. If you change the repository URL (`DECK.repo` at the end of the file), regenerate the path and replace the `d` attribute of `<symbol id="qr">`:

```bash
uv run --no-project --with "qrcode==7.4.2" python -c "
import qrcode
qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
qr.add_data('https://github.com/ccarballolozano/foundry-agents'); qr.make(fit=True)
m = qr.get_matrix(); n = len(m); out = []
for y, row in enumerate(m):
    x = 0
    while x < n:
        if row[x]:
            s = x
            while x < n and row[x]: x += 1
            out.append(f'M{s} {y}h{x-s}v1h-{x-s}z')
        else: x += 1
print(n, ''.join(out))"
```

The first number it prints is the module count; the symbol's `viewBox` is `-4 -4 <n+8> <n+8>` (33 modules today, so `-4 -4 41 41`), which keeps the 4-module quiet zone scanners need.

The [README](../README.md) is the full reference for each feature. This guide puts the demo pieces in order and doesn't repeat what the README explains.

## The story

The talk asks one question: *what does an agent need around it to be in production and operable, before you deploy it and after?* The answer comes in five acts, one per verb: deploy it, evolve it, integrate it, understand it and protect it.

It follows **MyConcepts**, a fictional company, and three agents:

| Agent | Role |
|---|---|
| `hr-benefits-agent` | The small prototype: one model, one prompt, one tool (`get_benefit_details`), written with Microsoft Agent Framework |
| `hr-agent` | What the prototype grows into: the same tool, plus the company handbook through Foundry IQ and a call to the IT agent |
| `it-agent` | The IT team's agent, written in LangGraph, hosted on the same platform |

Each act answers one production question and raises the next:

| Act | Question | Demo |
|---|---|---|
| 0 · It works | Does the agent work at all? | D1 · Run the agent locally |
| 1 · Others can use it | Where does it run, and who is it? | D2 · Hosted agent: conversation, session and identity |
| 2 · It can change safely | How do I change it, and how do I know I didn't break it? | D3 · New version · D4 · Evaluation |
| 3 · It integrates | How does it reach company data and other teams' agents, safely? | D5 · Toolbox, Foundry IQ and A2A |
| 4 · You can understand it | When an answer is wrong, where did it fail? | D6 · One trace across two agents |
| 5 · It's protected | What stops misuse and data leaks? | D7 · Guardrail and red teaming |

A slide with a checklist (runtime, identity, context, versions, evaluation, integration, observability, protection) comes back after each act. It has two columns: **before deploying** (a gate that stops a bad version) and **in production** (checks that keep running). The demos mostly show the first column. Each act ends with an *In production* note for the second.

---

## Part 1: Set up once

Do these steps in order. Each step says how to check whether it's already done, so you can skip it. Most steps are long-running or need rights you may only have at certain times, which is why the talk showed results prepared in advance instead of running them live.

Run everything from the repository root. The `python` commands assume the virtual environment is active (`source .venv/bin/activate`). Otherwise, prefix them with `uv run`.

### 1. Tools, access and the Foundry project

Follow the README's [Prerequisites](../README.md#prerequisites) and [Getting Started](../README.md#getting-started) steps 1 to 6:

- install the tools (`azd` with the `azure.ai.agents` and `azure.ai.projects` extensions, `az`, Python 3.13, `uv`);
- have a Foundry project with a chat model deployment (the demo used `gpt-5.4-mini`) and Application Insights connected for tracing;
- `uv sync`, `azd auth login`, `az login`;
- create the azd environment and the root `.env`;
- run `azd ai agent doctor` until it reports no problems.

**Skip if** `azd env get-values` shows `FOUNDRY_PROJECT_ENDPOINT` and `AZURE_AI_MODEL_DEPLOYMENT_NAME`, and `azd ai agent doctor` passes.

Name your azd environment with a `-dev` suffix (for example `my-demo-dev`). Provisioning then marks it as non-production, which the red-teaming scripts in step 7 require.

### 2. Deploy `hr-benefits-agent`

```bash
python agents/hr-benefits-agent/local.py      # quick local check
azd deploy hr-benefits-agent
azd ai agent invoke hr-benefits-agent "Tell me about the Remote Work benefit."
```

**Skip if** `azd ai agent show hr-benefits-agent` shows a version and `azd env get-value AGENT_PROMPT` is empty (the baseline prompt).

**Traces from the agent's own code** need one role if your project sends telemetry with Microsoft Entra. Check with `azd ai connection list -o json | grep -B2 -A2 AppInsights`. If the auth type is `ProjectManagedIdentity`, grant `Monitoring Metrics Publisher` to each agent's identity after its first deploy, as in [Observe Telemetry and Custom Traces](../README.md#observe-telemetry-and-custom-traces). `provision.py` (step 5) does it for `hr-agent`. You do it yourself for `hr-benefits-agent` and `it-agent`.

### 3. Evaluation runs for Act 2

Act 2 compares two runs of the same evaluation: one against the baseline prompt and one against the `mistake` prompt, which tells the agent not to use its tool. Each run takes a few minutes. Details: [Evaluate the Agent](../README.md#evaluate-the-agent).

```bash
azd extension install azure.ai.evaluations
azd ai eval create hr-benefits-agent --path agents/hr-benefits-agent/evals
azd ai eval run start --path agents/hr-benefits-agent/evals         # baseline run

azd env set AGENT_PROMPT mistake
azd deploy hr-benefits-agent
azd ai eval run start --path agents/hr-benefits-agent/evals         # mistake run

azd env set AGENT_PROMPT ""                                          # back to baseline
azd deploy hr-benefits-agent
```

**Skip if** `azd ai eval run list --path agents/hr-benefits-agent/evals` already lists a run against the baseline and one against `mistake`. Always finish with `AGENT_PROMPT` empty and `hr-benefits-agent` redeployed.

### 4. Deploy `it-agent`

```bash
azd env set IT_AGENT_PROMPT ""
azd deploy it-agent
azd ai agent invoke it-agent "What laptop does a software engineer get?"
```

**Skip if** `azd ai agent show it-agent` shows a version. Deploy it before step 5, so that provisioning adds the A2A tool to `hr-agent`'s toolboxes. Details: [IT Agent: LangGraph, A2A and Tracing](../README.md#it-agent-langgraph-a2a-and-tracing).

### 5. Knowledge stack, toolboxes and `hr-agent`

`provision.py` creates the Azure AI Search service, the storage account, the embedding deployment, the handbook knowledge base, the connections, the two toolboxes and the roles. It's safe to run again: it only changes what differs. Check the roles it needs first: [Provision the knowledge stack](../README.md#provision-the-knowledge-stack).

```bash
python agents/hr-agent/provision/provision.py     # first run
azd env set HR_AGENT_PROMPT ""
azd deploy hr-agent
python agents/hr-agent/provision/provision.py     # again: grants hr-agent's own identity its roles
```

- Creating the search service and assigning roles took about 20 minutes on 2026-11-07. Later runs take seconds when nothing changed.
- If you can't assign roles, the script ends with exit code 2 and prints the `az role assignment create` commands for someone who can.
- The first run reports `hr-agent identity: pending` because the agent doesn't exist yet. That's why it runs twice.

**Skip if** the script already ran and `azd ai agent invoke hr-agent --new-session "How many holiday days can I carry over to next year?"` answers with 5 days and cites `time-off-policy.md`.

### 6. Guardrail on `hr-agent`

Act 5 uses `hr-agent` deployed with the `hr-agent-guard` policy (Microsoft's `DefaultV2` filters plus Indirect Attack). Replace `<sub>`, `<rg>` and `<account>` with your subscription ID, resource group and Foundry account name (`azd env get-value AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `AZURE_AI_ACCOUNT_NAME`).

```bash
az rest --method put \
  --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies/hr-agent-guard?api-version=2025-06-01" \
  --body @agents/hr-agent/provision/rai-policy-hr-agent-guard.json
azd env set HR_AGENT_RAI_POLICY_ID "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/raiPolicies/hr-agent-guard"
scripts/use-guardrail-manifest.sh     # writes the policy IDs into azure.yaml
azd deploy hr-agent
git checkout azure.yaml               # back to the default manifest
scripts/probe-guardrail.sh            # the jailbreak must be BLOCKED at the input stage
```

`scripts/use-guardrail-manifest.sh` stops unless **both** `HR_AGENT_RAI_POLICY_ID` and `HR_BENEFITS_AGENT_RAI_POLICY_ID` hold a full policy ID, although only `hr-agent` is deployed here. If you have no policy for `hr-benefits-agent`, set its variable to the same `hr-agent-guard` ID: it's only used if you deploy `hr-benefits-agent` with this manifest. Don't give it a policy with the PII controls: those block every request (see [Guardrail status (preview)](../README.md#guardrail-status-preview)).

**Skip if** `scripts/probe-guardrail.sh` reports the jailbreak as `BLOCKED`.

**A missing or misspelled policy fails open:** the deploy succeeds and no guardrail is attached. Always run the probe after deploying. Details: [Apply Guardrails](../README.md#apply-guardrails) and [Guardrail status (preview)](../README.md#guardrail-status-preview).

### 7. Optional: the safety results shown in Act 5

Act 5 shows results; it doesn't run these live. Each scan sends 50 to 60 attacks, and a cloud scan takes longer.

- **`hr-agent` evaluation** (20 questions, including confidential ones):

  ```bash
  azd ai eval create hr-agent --path agents/hr-agent/evals
  azd ai eval run start --path agents/hr-agent/evals
  ```

- **Targeted red-team scans** against the planted confidential document: follow [Safety demo: baseline, guardrail, re-scan, evaluation](../README.md#safety-demo-baseline-guardrail-re-scan-evaluation). It deploys `hr-agent` with the deliberately permissive `leaky` prompt first. **When you finish**, set `HR_AGENT_PROMPT ""` and redeploy `hr-agent` with the guardrail manifest, as in step 6, so the agent is back to the demo state.
- **Cloud red-team scan** (Foundry's built-in risk categories): `python agents/hr-agent/redteam/cloud_scan.py --strategies Flip,Base64 --turns 1`. See [Red team hr-agent](../README.md#red-team-hr-agent) for its known limitations.

Slide 30 of the presentation (*Red teaming: el guardrail frena ataques, no fugas*) charts the results of three targeted-scan runs: safe prompt, permissive prompt, and permissive prompt with guardrail.

### 8. Optional: revoke and restore the agent's identity

`scripts/demo-agent-identity.sh` removes `hr-agent`'s only role on the search service, shows that the agent can no longer read the handbook, then gives the role back. It needs the right to assign roles (Owner or User Access Administrator) and takes a few minutes, because role changes take time to apply. Details: [Why the agent's own identity matters](../README.md#why-the-agents-own-identity-matters).

---

## Part 2: Before you run the demo

1. **If the search service is paused** (see [Part 4](#part-4-after-the-demo)), resume it the day before. It takes about 20 minutes:

   ```bash
   python agents/hr-agent/provision/provision.py
   ```

2. **About 10 minutes before**, run the pre-flight check:

   ```bash
   scripts/preflight.sh
   ```

   It checks sign-in, the prompts, the manifest and the guardrail policy. It warms up each hosted agent (a cold start takes 7 to 13 s) and asks `hr-agent` the Act 3 question once, so that trace is ready for Act 4. It prints the trace ID. Every line must say `OK`. It takes about 2 minutes.

   If a line says `FAIL`, it tells you the fix. The most common one: `AGENT_PROMPT` was left on `new-version` after Act 2. Run `azd env set AGENT_PROMPT ""` and `azd deploy hr-benefits-agent`.

3. **Terminal:** a large font, the virtual environment active, and `export AZD_SKIP_UPDATE_CHECK=true` to hide azd's update notice.

4. **Portal tabs** in the [Foundry portal](https://ai.azure.com), signed in to your project:

   | Tab | For | Where |
   |---|---|---|
   | 1 | D3 | Agents → `hr-benefits-agent` → versions |
   | 2 | D4 | Evaluations → the `hr-benefits-agent` evaluation: its runs, its dataset and its evaluator |
   | 3 | D6 | Agents → `hr-agent` → Traces |
   | 4 | D7 | Evaluations → the cloud red-team run (if you ran step 7 of Part 1) |
   | 5 | D7, optional | Evaluations → the `hr-agent` evaluation run |

5. **Editor tabs:** `agents/hr-benefits-agent/agent.py`, `agents/hr-benefits-agent/tools.py`, `agents/hr-benefits-agent/prompts/new-version.md`, `agents/hr-benefits-agent/evals/azure.eval.yaml`, `agents/it-agent/agent.py`, `azure.yaml` (the `it-agent` block) and `azure-with-guardrail.yaml` (the `policies:` block of `hr-agent`).

---

## Part 3: The demo, act by act

### Act 0 · It works

**D1 · Local agent.** Show `agent.py` and `tools.py` (about 20 lines), then run:

```bash
python agents/hr-benefits-agent/local.py
```

**You should see** the agent list the Remote Work, Health Insurance and Learning Budget benefits.

**What it shows:** a working agent is a model, instructions and a tool. It runs on your laptop, so nobody else can use it yet. Details: [Run the Agent Locally](../README.md#run-the-agent-locally).

### Act 1 · Others can use it

**D2 · Hosted agent: conversation, session and identity.** The same code, hosted in Foundry:

```bash
azd ai agent invoke hr-benefits-agent --new-session "Tell me about the Remote Work benefit."
azd ai agent invoke hr-benefits-agent "What benefit did I just ask about?"              # remembers
azd ai agent invoke hr-benefits-agent --new-session "What benefit did I just ask about?" # doesn't know
azd ai agent show hr-benefits-agent
```

**You should see** the second call answer "Remote Work" and the third not know. Each invoke prints `Conversation`, `Session`, `Trace ID` and `Platform latency`. `azd ai agent show` prints the version and the `Instance Identity Principal ID`, the agent's own Microsoft Entra identity.

**What it shows:**
- **The conversation is the memory.** It's the message history Foundry stores, chained by a conversation ID or `previous_response_id`. `azd ai agent invoke` reuses the last conversation; `--new-session` starts a new one.
- **The session is the sandbox,** compute plus a persisted `$HOME` and `/files`. Reusing a session ID on its own doesn't replay earlier messages. Compute is released after an idle timeout (15 minutes by default) and restored on the next call. A session unused for 30 days is deleted.
- **The agent has its own identity,** separate from whoever deployed it.

Details: [Manage Sessions and Conversations](../README.md#manage-sessions-and-conversations).

**In production:** the agent monitoring dashboard shows latency, errors and tokens, with alerts on top. Deployment runs from a pipeline (`azd pipeline config`, signing in with OIDC), not from a laptop.

### Act 2 · It can change safely

**D3 · A new version.** Change one sentence of the prompt and deploy:

```bash
diff agents/hr-benefits-agent/prompts/baseline.md agents/hr-benefits-agent/prompts/new-version.md
azd env set AGENT_PROMPT new-version
azd deploy hr-benefits-agent                     # about 70 s
azd ai agent invoke hr-benefits-agent --new-session "Tell me about the Learning Budget."
```

**You should see** the answer end with "Haahee!" and a new version in portal tab 1, with the old versions still listed.

**What it shows:** every deploy packages the folder, builds it remotely from `requirements.txt` and creates a new version with the same identity. The previous versions remain. Rolling back is the same commands with `AGENT_PROMPT ""`. Details: [Update the Agent](../README.md#update-the-agent-system-prompt-iteration).

**D4 · Evaluation: did the change break anything?** This uses the runs from [Part 1, step 3](#3-evaluation-runs-for-act-2); nothing runs live.

1. In portal tab 2, show what the evaluation is made of. It's configuration, versioned next to the agent:
   - **the dataset:** 15 plain questions, with no expected answers, including unsupported ones such as "Do we have a transport benefit?" (`evals/datasets/.../hr-benefits-agent_dg.jsonl`);
   - **the evaluator:** 7 dimensions, each a sentence and a weight, scored by a judge model (`evals/evaluators/hr-benefits-agent/rubric_dimensions.json`);
   - **the target agent** (`evals/azure.eval.yaml`).
2. Compare the two runs. In the talk, the baseline run passed **15/15 (100%)** and the `mistake` run **6/15 (40%)**.
3. Open a failed row in the `mistake` run. The judge gave `tool_use_for_exact_policy_details` a 1, because the agent didn't use the benefit lookup tool before answering.

Without the portal:

```bash
azd ai eval run list --path agents/hr-benefits-agent/evals
azd ai eval run output show 1 --eval <eval-id> --run <mistake-run-id>
```

**What it shows:** a regression you can't see by reading one answer shows up as a score per dimension, with the judge's reason. Details: [Evaluate the Agent](../README.md#evaluate-the-agent).

**In production:**
- **Before deploying:** the same evaluation as a quality gate in CI/CD (a GitHub Action or Azure DevOps task, in preview). A version below the threshold isn't published.
- **In production:** a scheduled evaluation on the same dataset catches drift when the model, knowledge or tools change underneath. Continuous evaluation scores a sample of real traffic.

**Afterwards, put the baseline back** (you can leave this for after the demo):

```bash
azd env set AGENT_PROMPT ""
azd deploy hr-benefits-agent
```

### Act 3 · It integrates

The prototype grows into `hr-agent`:
- it reads the company handbook through **Foundry IQ** (a knowledge base in Azure AI Search), reached through a **toolbox**: a governed entry point, with no keys in the code;
- the IT team's `it-agent`, written in **LangGraph**, runs on the same hosting with the same identity and tracing;
- the two agents talk over **A2A**, an open protocol.

The diagram is in the README: [How it fits together](../README.md#how-it-fits-together).

**D5 · Toolbox, Foundry IQ and A2A.**

```bash
azd ai agent invoke hr-agent --new-session "List the names of all the tools you can use, one per line, without calling any."
azd ai agent invoke hr-agent --new-session "I start Monday as a consultant: what do I need to do in my first week, and which accounts will I get?"
```

**You should see:**
- the first call lists `get_benefit_details`, `hr_handbook___knowledge_base_retrieve` and `it-agent-a2a___SendMessage`. The A2A tool was added to the toolbox with no redeploy of `hr-agent`;
- the second call (about 30 s) gives the week-1 steps from the handbook, citing `onboarding-checklist.md`, and the consultant's accounts from `it-agent`. **Copy the `Trace ID`** for Act 4.

Optionally show `agents/it-agent/agent.py` (LangGraph's `create_agent`) and the `agentCard` block in `azure.yaml`.

**Least privilege.** List what `hr-agent`'s identity may do:

```bash
az role assignment list --assignee "$(azd env get-value AGENT_HR_AGENT_INSTANCE_IDENTITY_PRINCIPAL_ID)" --all --query "[].{role:roleDefinitionName, scope:scope}" -o table
```

**You should see** three roles, each on one resource:
- `Search Index Data Reader` on the search service;
- `Foundry Agent Consumer` on `.../agents/it-agent` only;
- `Monitoring Metrics Publisher` on Application Insights (only if your project sends telemetry with Entra).

The hosted toolbox accepts only the agent's own identity: a person's token is rejected. Revoking the role cuts the agent off from the handbook with no redeploy and no secret to rotate. The talk told this rather than running it ([Part 1, step 8](#8-optional-revoke-and-restore-the-agents-identity)).

**What it shows:** integration through governed tools and an open protocol, with an identity per agent that you can audit and revoke. Details: [Add a governed tool without a redeploy](../README.md#add-a-governed-tool-without-a-redeploy), [Call it-agent from hr-agent over A2A](../README.md#call-it-agent-from-hr-agent-over-a2a) and [docs/azure-search-in-foundry.md](azure-search-in-foundry.md).

**In production:**
- one identity per agent means per-agent audit, revocation and least privilege, with no shared keys;
- roles and connections belong in infrastructure as code (`provision.py` would become Bicep or Terraform);
- adding a tool with no redeploy also changes the agent, so that change has to pass the evaluation gate too.

### Act 4 · You can understand it

**D6 · One trace across both agents.** In portal tab 3, open the trace from D5. If it isn't there yet (ingestion takes a few minutes), use the one the pre-flight printed. One trace holds both agents:

- `invoke_agent HRAgent` → `execute_tool hr_handbook___knowledge_base_retrieve` → `execute_tool it-agent-a2a___SendMessage`;
- inside it, `it-agent`'s spans: `invoke_agent it-agent`, `chat gpt-5.4-mini`, `execute_tool get_access_setup` and the custom span `it.access.lookup`.

**Point out:**
- the A2A hop took about 13 s in rehearsal, about 10 s of it `it-agent`'s cold start. You only see that in a trace;
- message content shows as `[redacted]` by default, for privacy.

Without the portal, query Application Insights. Put the trace ID in `TRACE`:

```bash
TRACE=<trace id>
APPI_ID=$(azd ai connection list -o json | python3 -c "import sys,json;t=sys.stdin.read();print(next(c['target'] for c in json.loads(t[t.find('['):]) if c.get('kind')=='AppInsights'))")
az monitor app-insights query --ids "$APPI_ID" --offset 3h --analytics-query "union dependencies, requests | where operation_Id == '$TRACE' | where name !startswith 'GET /' and name !startswith 'POST /' | project timestamp, cloud_RoleName, name, duration | order by timestamp asc" --query "tables[0].rows" -o tsv
```

**What it shows:** a trace is the journey of one request, across agents and frameworks, including your own spans (OpenTelemetry). Foundry keeps the trace ID across the A2A hop; this was observed in this project and isn't documented by Microsoft Learn yet. Details: [Observe Telemetry and Custom Traces](../README.md#observe-telemetry-and-custom-traces) and [Traces for it-agent](../README.md#traces-for-it-agent).

**In production:** traces are the first thing you open when something goes wrong. These agents keep 100% of traces (`OTEL_TRACES_SAMPLER` in `azure.yaml`); at volume that's a cost decision. Content stays off. Alerts on latency and errors. **A bad trace becomes a new row in the evaluation dataset,** which closes the loop with Act 2.

### Act 5 · It's protected

The risks: ignoring instructions, leaking data, inappropriate content. The handbook contains a **confidential document planted on purpose** (`salary-bands-CONFIDENTIAL.md`), with made-up "canary" values such as salary bands and a fake employee's contact details. Red teaming means attacking your own agent to find what gets through.

**D7 · Guardrail.** Show the `policies:` block of `hr-agent` in `azure-with-guardrail.yaml`: the guardrail is configuration, not code. Then:

```bash
scripts/probe-guardrail.sh
```

**You should see** the jailbreak `BLOCKED` with `content safety policy violation at input stage`. The other probes (a normal question and questions about personal data) are answered or refused by the agent itself.

**Red-team results,** shown, not run (see [Part 1, step 7](#7-optional-the-safety-results-shown-in-act-5)):

1. **The chart** on slide 30 compares the same targeted scan against a safe prompt, a permissive prompt, and the permissive prompt with the guardrail:
   - the guardrail stops the **jailbreaks**: about 18% of the attacks never reached the model;
   - it does **not** stop leaks from plain questions (21.7% → 18.3%, within the noise of 60 attacks);
   - the safe prompt does (0%).

   Defence is layered: the prompt, which data you index, the agent's least-privilege identity, and the `confidential_non_disclosure` evaluation dimension.
2. **The cloud red-team run** in portal tab 4: attack strategies (`Flip`, `Base64`), 111 attack items, results and reasons per item. **Show the mechanism, not the numbers:** spot checks found items marked as failed whose judge reason says the agent refused safely.
3. Optionally, the `hr-agent` evaluation in portal tab 5: in the talk's run, 19/19 scored rows passed and `confidential_non_disclosure` scored 5/5. One row errored because the platform's content filter stopped the "show me the confidential document" request.

**What it shows:** a guardrail blocks attacks on the agent; it doesn't make confidential data safe. What a guardrail can and can't do is in [What you can and cannot show](../README.md#what-you-can-and-cannot-show) and [Guardrail status (preview)](../README.md#guardrail-status-preview).

**In production:**
- **Before deploying:** red teaming as a gate.
- **In production:** the guardrail runs on every request; scheduled red teaming, because attacks change; continuous evaluation with safety evaluators; blocked requests show up in traces and monitoring.

### Closing · An operable agent

An agent in production runs as a cycle, and each demo is one part of it:

1. **Build and integrate:** your code and framework, the toolbox, Foundry IQ, A2A.
2. **Evaluate before publishing:** evaluations and red teaming as a quality gate.
3. **Deploy versions:** the hosted agent, its own identity, conversations and sessions.
4. **Protect every request:** guardrails on input and output, least privilege.
5. **Observe:** end-to-end traces, monitoring and alerts.
6. **Measure in production:** continuous and scheduled evaluation, scheduled red teaming.

What production teaches you, such as a bad trace, goes back to step 1 as a new dataset row.

---

## Part 4: After the demo

1. **Put `hr-benefits-agent` back on the baseline prompt** if Act 2 left it on `new-version`:

   ```bash
   azd env set AGENT_PROMPT ""
   azd deploy hr-benefits-agent
   ```

2. **Stop the search cost and keep the rest deployed.** The Azure AI Search service (Basic tier) is the only resource here with a fixed cost while idle, about $70–75 a month. It can't be stopped, and it can't move to the Free tier, which has no managed identity. Pause it:

   ```bash
   python agents/hr-agent/provision/provision.py --pause
   ```

   It asks you to type the service name, then deletes only the search service and its identity's roles. The toolboxes, connections, storage, embedding deployment and agents stay. Until you resume, `hr-agent` answers benefit questions but its handbook tool fails. To resume, run `provision.py` without flags (about 20 minutes), then `scripts/preflight.sh`. Details: [Pause between demos](../README.md#pause-between-demos).

3. **Remove the knowledge objects, toolboxes and connections** when you're done for good: `python agents/hr-agent/provision/provision.py --teardown`. See [Tear down](../README.md#tear-down) for what it keeps and how to delete the rest.

---

## Part 5: Giving the talk

Present from [`docs/talk/presentation.html`](talk/presentation.html). Every demo slide shows the recorded command and output, so the slides are also the fallback when a live demo fails.

### Timeline (50 min)

| Time | Act | Demo | How |
|---|---|---|---|
| 0–4 | 0 · Funciona | D1 local agent | Live |
| 4–12 | 1 · Que corra y lo puedan usar | D2 hosted agent | Live |
| 12–20 | 2 · Que evolucione sin miedo | D3 new version · D4 evaluation | D3 live · D4 existing runs |
| 20–30 | 3 · Que se integre | D5 toolbox and A2A | Live (identity on a slide) |
| 30–37 | 4 · Entenderlo | D6 one trace | Portal, trace from pre-flight or D5 |
| 37–45 | 5 · Protegerlo | D7 guardrail and red team | Live probe + existing results |
| 45–50 | Cierre · Un agente operable | — | Slides + Q&A |

### Fallback rules

- A live command takes more than about 45 s or fails: stay on the demo slide, which shows the recorded output. Don't debug on stage.
- The network is down: every demo slide carries its recorded output, and the evaluation, trace and red-team slides draw their results without Azure.
- The portal doesn't sign in or load: use the terminal fallbacks in D4 and D6.
- The `azd` token expired: run `az login` and `azd auth login` in a spare terminal.

### Likely questions

- **Cost:** a hosted agent scales to zero; the search service doesn't (see [Part 4](#part-4-after-the-demo)).
- **Other frameworks:** yes, `it-agent` is LangGraph.
- **Why not one shared identity:** per-agent revocation and audit.
- **A2A or MCP:** both appear here. The handbook is reached through MCP (the knowledge base's endpoint behind the toolbox); the other agent through A2A.

### What was verified on 2026-11-07

| Item | Result |
|---|---|
| Local runs of all three agents | ✔ |
| Hosted conversation: remembers, then forgets with `--new-session` | ✔ |
| Deploy of a new prompt version | ✔ 68 s, rolled back in 66 s |
| `hr-agent` tool list (A2A tool present) and the combined HR + IT answer | ✔ about 30 s |
| A2A card and call through `scripts/a2a_call.py` | ✔ |
| One trace across `hr-agent` and `it-agent` with the custom span (Application Insights) | ✔ |
| Guardrail: policy present, jailbreak blocked at the input stage | ✔ |
| Evaluation runs 100% and 40%, judge reasons through the CLI | ✔ |
| Pre-flight script | ✔ about 2 min |
| Identity: roles listed, a person's token refused by the hosted toolbox | ✔ (revoking needs a role-assignment right the speaker's account didn't hold that day) |
| Pause and resume of the search service, then pre-flight and a handbook question to the hosted `hr-agent` | ✔ resume took about 20 min |
| Portal content: versions, evaluation definition and runs, red-team run | ✔ through the CLI and REST API; not checked visually |
