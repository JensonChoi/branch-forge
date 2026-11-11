---
name: branchforge-search
description: Explore Python stdin/stdout solutions against visible tests using bounded BranchForge searches.
---

Collect a VisibleProblem with input/output formats and at least one visible test. Label agent-generated tests and explain coverage. Explicitly select fake or real provider; never infer it from model name. Explain model, algorithm, call/candidate/time limits before start_search. Use an idempotency key for retries. Poll get_search_status and honor cancellation via cancel_search until terminal. Report selected node, visible reward, termination and measured usage; fetch code with get_candidate. Real runs need spending authorization; host subscriptions are not provider credentials. Do not promise hard token/dollar ceilings or quality improvements.

Use the BranchForge MCP tools for scheduling and enforcement; never reproduce search policies in prose or execute candidate code on the host. Jobs belong to the MCP process and stop when it exits.
