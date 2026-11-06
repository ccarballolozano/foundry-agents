# Azure AI Search in Foundry: terms, options and what we can do with it

This is a reference for the team, not a demo script. It answers three questions:

1. What are the terms and options Foundry offers today for using Azure AI Search from an agent?
2. Which one does `hr-agent` use, and why?
3. What can we actually do and see with it, step by step, and what did we test?

Every statement about Foundry is tied to a numbered source in [Sources](#sources), so anyone can check it. Statements that come from our own runs are marked **Tested**. Statements that we could not verify are marked **Not verified** and say why.

Test environment for all **Tested** results: 2026-11-06, Sweden Central, Foundry project with `gpt-5.4-mini`, Azure AI Search Basic tier, search API `2026-08-01-preview`, `azure-search-documents` 12.1.0b2, `azd` 1.37.2, `agent-framework-foundry-hosting` 1.0.0b261030.

## 1. Terms

| Term | Meaning (source) |
|---|---|
| **Foundry IQ** | The managed knowledge layer for enterprise data. It consists of knowledge bases, knowledge sources, and native integrations with Azure OpenAI in Foundry Models and Foundry Agent Service. It is built on Azure AI Search agentic retrieval [1][2]. |
| **Knowledge base** | A top-level object that groups one or more knowledge sources under a single endpoint and controls how they are queried and how results are returned [2][11]. A knowledge base lives in Azure AI Search. Several agents can share one [1]. |
| **Knowledge source** | A connection to indexed or remote content. *Indexed* sources (Azure Blob Storage, OneLake, SharePoint, an existing search index) are ingested and chunked, vectorised and refreshed for you. *Remote* sources (SharePoint through the Copilot Retrieval API, the web through Grounding with Bing) query the external system at retrieval time [2]. |
| **Agentic retrieval** | The retrieval engine behind a knowledge base: an LLM can decompose a question into sub-queries, run them in parallel, rerank semantically and merge the results [1][2]. Foundry IQ is the Foundry-facing product; agentic retrieval is the engine, also usable directly through the Azure AI Search APIs [2]. |
| **Retrieval reasoning effort** | How much LLM planning is used: `minimal` (no LLM, up to 10 sources), `low` (up to 3 sources and 3 sub-queries), `medium` (up to 5 and 5, iterative) [2]. Query planning happens at `low` and `medium` [2]. The value `auto` exists in `2026-08-01-preview` [8]. |
| **Extractive data / answer synthesis** | Extractive data returns raw passages with references so the agent reasons over them. Answer synthesis has the knowledge base write the answer. The FAQ recommends extractive data for most Foundry IQ scenarios and answer synthesis for standalone applications [2]. |
| **Project connection** | A Foundry project object that holds how a tool is reached and with which identity. Credentials live on the connection, never in agent code [6]. Connections appear under **Connected resources** [9]. |
| **`RemoteTool` connection** | The connection kind for an MCP endpoint. For Foundry IQ it targets the knowledge base's MCP endpoint [3]. |
| **Azure AI Search connection (`CognitiveSearch`)** | The connection kind for a search service itself, created under **Connected resources > Add connection > Azure AI Search** [5][9]. It is what the Azure AI Search tool uses [5]. |
| **Toolbox** | A managed MCP endpoint that lets you reuse tools across agents and runtimes and centralise credentials, versioning and policy [5]. |

## 2. The options available today

There are four documented ways to use Azure AI Search from Foundry.

| | **A. Foundry IQ knowledge base, prompt agent** | **B. Foundry IQ knowledge base, hosted agent through a toolbox** | **C. Azure AI Search tool** | **D. Knowledge base from your own code** |
|---|---|---|---|---|
| What the agent calls | `knowledge_base_retrieve` over MCP [3] | `knowledge_base_retrieve` over MCP, behind a toolbox [4] | A search **index**, by name [5] | The knowledge base API or an Azure SDK [2] |
| Connection | `RemoteTool`, auth `ProjectManagedIdentity` [3] | `RemoteTool`, auth `agentic-identity` [4][6] | `CognitiveSearch` (Azure AI Search) [5] | None from Foundry; your own auth [2] |
| Identity that reads | The project's managed identity, needs `Search Index Data Reader` [3] | The agent's own identity, needs `Search Index Data Reader` [4][6] | Keyless: the Foundry **account**'s system-assigned identity, needs `Search Index Data Contributor` and `Search Service Contributor` [5] | Yours |
| What you build | A knowledge source and a knowledge base [3] | The same, plus a toolbox [4] | An index with a searchable text field, a vector field and a retrievable source URL field [5] | The same as A |
| Limits stated in the docs | Only `knowledge_base_retrieve` is supported in Agent Service; SDK support is Python and REST [3] | As A | One index per tool; the search service and the agent must be in the same tenant [5] | Agent Service is not required [2] |
| Can sit in a toolbox | n/a | Yes [4] | Yes [5] | n/a |

The Azure AI Search tool page itself points to Foundry IQ for "a managed knowledge base experience" [5].

**`hr-agent` uses option B** for the hosted agent. For local runs it uses the same knowledge base through a second toolbox whose connection has auth `user-entra-token`, which makes the knowledge base see the developer instead of the agent [6].

### Identity choices on the connection [6]

| `authType` | Whose identity reaches Azure Search | Use it for |
|---|---|---|
| `project-managed-identity` | The project's managed identity | Service-to-service calls with no user context |
| `agentic-identity` | The agent's own identity | Per-agent audit and least privilege. A user token is rejected on purpose |
| `user-entra-token` | The signed-in Microsoft Entra user | Calls that must run as the user |

Per-user *document* permissions are a separate mechanism: the caller passes a user token in the `x-ms-query-source-authorization` header and the knowledge source must carry permission metadata [3]. **We do not use it** (see section 4).

## 3. What is generally available and what is preview

The knowledge base API has a stable version, `2026-04-01`, and preview versions on top of it [8].

| Capability | Status | Source |
|---|---|---|
| Stable API `2026-04-01`: minimal, extractive retrieval | Generally available | [8] |
| `azureBlob`, `searchIndex`, `indexedOneLake` and `web` knowledge sources | Generally available in `2026-04-01` | [8] |
| Indexed and remote SharePoint knowledge sources | Preview | [8] |
| LLM query planning (`low`/`medium` reasoning effort), answer synthesis, multi-turn messages | Preview (removed from the stable API) | [3][8] |
| The knowledge base MCP endpoint for Agent Service (`2026-08-01-preview`) and the `RemoteTool` connection | Preview | [3] |
| Foundry portal and Azure portal access to agentic retrieval | Preview-only access to all agentic retrieval features | [1] |

**Where `hr-agent` sits:** an `azureBlob` knowledge source (generally available kind), with `low` reasoning effort (preview), extractive output, the preview MCP endpoint and a `RemoteTool` connection. The preview parts are the ones that give query planning and the Agent Service integration. A generally-available-only setup would use API `2026-04-01` and `minimal` effort, with no LLM query planning. **We have not built or tested that variant.**

`gpt-5.4-mini`, which we use for query planning, is listed as supported from `2026-05-01-preview` [8]. The FAQ states that only gpt-4o, gpt-4.1 and gpt-5 series models are supported for query planning [2].

## 4. What we built, and why

| Decision | Our reason | Basis |
|---|---|---|
| Knowledge base through a toolbox (option B), not the Azure AI Search tool | The agent's **own** identity reads, with one read-only role. The tool's keyless mode uses the Foundry account's identity with broader roles | [4][5][6] |
| Blob knowledge source from Markdown files | Foundry IQ creates and refreshes the index; we do not design index fields | [2] |
| `low` reasoning effort, `gpt-5.4-mini` | Query planning on, at the cheaper planned level | [2][8] |
| Extractive output | Recommended for agent scenarios; `hr-agent`'s model writes the answer and citations, so there is one LLM answer per question | [2] |
| `require_approval: never`, `allowed_tools: [knowledge_base_retrieve]` | The tool only reads. It is the only tool Agent Service supports for a knowledge base | [3][7] |
| Unversioned toolbox endpoint | A new toolbox version needs no agent redeploy | [7] |

**We did not benchmark** the knowledge base against the Azure AI Search tool on our handbook. The docs cite a benchmark for agentic retrieval over single-shot retrieval [2]; we did not reproduce it.

**What we did not configure, and the consequence.** Per-user document permissions are enforced only when the knowledge source supports them and they were explicitly configured [2]. Ours were not. So **any caller with `Search Index Data Reader` gets every document, including the planted confidential one** (step 3 below). In this repository, confidentiality therefore rests on the system prompt, the evaluation and a least-privilege identity, not on the knowledge base. Document-level permissions are listed as future work.

## 5. The portal's Knowledge page

The docs say that on the Foundry portal's **Knowledge** tab you "create or connect to an existing search service that supports agentic retrieval" [1], and that connections of type Azure AI Search appear under **Connected resources** [9].

They do **not** state how the Knowledge tab decides which search services to list. **Our assumption**, not documented: it lists search services attached to the project as an Azure AI Search connection. `provision.py` therefore also creates `hr-search` (kind `CognitiveSearch`, auth `ProjectManagedIdentity`). No agent uses it. **Not verified** in the portal (we could not sign in from the automation).

The extra roles in the docs (`Search Index Data Contributor`, `Search Service Contributor` on the Foundry account's identity) are documented for the **Azure AI Search tool** [5]. We found no documentation of which roles the Knowledge page needs, so `provision.py` does not grant them.

## 6. What we can do and see, step by step

All commands run from the repository root with `az login` and `azd auth login` done and the azd environment selected. "Role" is what the person running it needs.

| # | What you can show | How | Observed result | Time | Status |
|---|---|---|---|---|---|
| 1 | What is configured in Azure AI Search | Commands below, step 1 | Knowledge base `hr-handbook-kb`: `extractiveData`, reasoning `low`, source `hr-handbook-ks`. Knowledge source status `active`, interval `1d` | seconds | Tested |
| 2 | What the agent's tool does: a direct retrieve with its activity log | Step 2 below | Activity: `modelQueryPlanning`, three parallel `azureBlob` queries, `agenticReasoning`. References: `time-off-policy.md` first for a carry-over question. The planning call used 908 input and 38 output tokens in 688 ms | 2 s | Tested |
| 3 | The knowledge base does not know what is confidential | Step 3 below | A salary question returns `salary-bands-CONFIDENTIAL.md` and the figure `68,910` in the payload, to a caller holding only the reader role | 2 s | Tested |
| 4 | How the agent reaches it: toolbox and connections | `azd ai toolbox show hr-agent-toolbox`, `azd ai toolbox show hr-agent-toolbox-dev`, `azd ai connection list` | Each toolbox has one tool `hr_handbook` (`knowledge_base_retrieve`, approval `never`). `hr-kb` is `RemoteTool` + `AgenticIdentityToken`; `hr-kb-dev` is `RemoteTool` + `UserEntraToken` | seconds | Tested |
| 5 | The agent calling both sources | `python agents/hr-agent/local.py "Am I eligible for the learning budget, and how do I get a course reimbursed?"` | Log shows `hr-agent using toolbox 'hr-agent-toolbox-dev'`, then `get_benefit_details` and `hr_handbook___knowledge_base_retrieve`, both succeeded, and an answer citing `learning-budget-claims.md` | about 15 s | Tested |
| 6 | The hosted agent's tool list | `azd ai agent invoke hr-agent "List the names of every tool you can call right now, exactly as named." --new-session` | `get_benefit_details`, `hr_handbook___knowledge_base_retrieve` | about 13 s (cold) | Tested |
| 7 | A document change reaches the agent | Edit a number in `knowledge/handbook/time-off-policy.md`, run `python agents/hr-agent/provision/provision.py`, ask again | Carry-over changed from 5 to 9 days in the answer after a 32 s provisioning run. Reverted the same way | about 45 s | Tested |
| 8 | A deleted document stops being retrievable | Delete a handbook file, run `provision.py`, ask about its content | The script finds the stale document in the index and rebuilds the knowledge base and source; the content is no longer returned. Retrieval is unavailable while it rebuilds | not timed, roughly a minute or two | Tested (earlier the same day) |
| 9 | A new governed tool without a redeploy | Add a tool to the toolbox, promote the version | The running hosted agent lists the new tool on its next request; rolled back afterwards | not timed, a few minutes | Tested (earlier the same day) |
| 10 | Why the agent's own identity matters | `scripts/demo-agent-identity.sh` (role: Owner or User Access Administrator, for example through PIM) | One read-only role; a user token refused by the hosted toolbox; revoke the role and the agent can no longer read the handbook; restore it and it answers again | not timed, a few minutes (role changes propagate with a delay) | Tested |
| 11 | Source selection is measured | `azd ai eval run start --path agents/hr-agent/evals` | Per-dimension scores including `source_selection` and `handbook_citation`; judge varies about ±0.5 between identical runs | about 2.5 min | Tested |
| 12 | Query plans and sub-queries in the Azure portal | Azure portal > the search service > knowledge base > query in the portal. The Azure portal is where you build and query knowledge bases; the Foundry portal is where you connect one to an agent [1][10] | The docs say the portal shows query plans, sub-queries and retrieval steps [2]. We show the same data from step 2 | n/a | **Not verified** (no portal sign-in) |
| 13 | The knowledge base on the Foundry **Knowledge** page | Foundry portal > Build > Knowledge | Expected to list the search service and `hr-handbook-kb` (see section 5) | n/a | **Not verified** |

### Commands for steps 1 to 3

All three were run exactly as written and returned the results above.

```bash
SEARCH="$(azd env get-value HR_AGENT_SEARCH_ENDPOINT)"
TOKEN="$(az account get-access-token --resource https://search.azure.com --query accessToken -o tsv)"
V=2026-08-01-preview
```

Step 1, what is configured:

```bash
curl -s "$SEARCH/knowledgebases/hr-handbook-kb?api-version=$V" -H "Authorization: Bearer $TOKEN"
curl -s "$SEARCH/knowledgesources/hr-handbook-ks/status?api-version=$V" -H "Authorization: Bearer $TOKEN"
```

Step 2, a direct retrieve with the activity log:

```bash
curl -s -X POST "$SEARCH/knowledgebases/hr-handbook-kb/retrieve?api-version=$V" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":[{"type":"text","text":"How many holiday days can I carry over to next year?"}]}],"includeActivity":true}'
```

Step 3, the confidentiality gap. Same call with the question `What is the salary band for a Senior Engineer?`. Look for `salary-bands-CONFIDENTIAL.md` in `references`.

### Suggestion for running these in a presentation

This is only a suggestion based on the measured times: steps 1 to 6 and 12 to 13 take seconds and are easy to run live. Steps 7 and 11 take under three minutes and can run while talking. Steps 8, 9 and 10 take longer (they were not timed) or need elevated roles, so their recorded results above are the better choice, with the commands as backup.

## Sources

Checked on 2026-11-06.

1. What is Foundry IQ? https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq
2. Foundry IQ frequently asked questions. https://learn.microsoft.com/azure/foundry/agents/concepts/foundry-iq-faq
3. Connect a Foundry IQ knowledge base to Foundry Agent Service. https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect
4. Quickstart: Add a Foundry IQ knowledge base to a hosted agent with a toolbox. https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-foundry-iq-hosted-agent
5. Connect an Azure AI Search index to Foundry agents. https://learn.microsoft.com/azure/foundry/agents/how-to/tools/ai-search
6. How toolbox authentication works in Microsoft Foundry. https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-authentication
7. Use a toolbox with a hosted agent. https://learn.microsoft.com/azure/foundry/agents/how-to/tools/use-toolbox-hosted-agent
8. Migrate agentic retrieval code to the latest version (API versions, what is stable and what is preview). https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-migrate
9. Add a new connection to your project. https://learn.microsoft.com/azure/foundry/how-to/connections-add
10. Try Azure AI Search for free (what each portal is for). https://learn.microsoft.com/azure/search/search-try-for-free
11. Create a knowledge base in Azure AI Search. https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base
