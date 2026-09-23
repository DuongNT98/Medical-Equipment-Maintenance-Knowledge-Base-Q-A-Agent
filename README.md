# HCR-C2-015 — Medical Equipment Maintenance Knowledge Base Q&A Agent

> **Category**: Cat 2 (multiple processing steps combined to complete one specific use case)
> **Industry**: Healthcare

## Overview

This agent answers maintenance questions about medical equipment by retrieving from a
per-manufacturer equipment-manual knowledge base. Given an equipment model, a maintenance
task, and an optional component, it returns the step-by-step procedure, the tools required,
any safety warnings — always reproduced verbatim from the source manual, never paraphrased or
summarized — a regulatory reference, and an escalation path for cases it cannot resolve.

It does not diagnose equipment faults, does not decide whether a procedure should be
performed, and does not replace the judgement of a qualified biomedical engineer — it surfaces
what the manual already says. It does not process patient data of any kind; its scope is
equipment records only.

The equipment inventory and manual knowledge base shipped with this template are a small
in-memory reference dataset for local development and testing. A real deployment must supply
its own inventory and knowledge-base backend covering the equipment it actually maintains.

This is an agent template built with the **AGENTIC STAR** development platform and the
**AgentCore Framework**. It is intended to be taken as a starting point: fork it, adapt it to
your own data and policies, and run it inside your own AGENTIC STAR deployment.

## Requirements

**This template does not run standalone.** It requires:

| Requirement | Notes |
|---|---|
| **AGENTIC STAR platform** | The agent connects to the platform at start-up. Without it, start-up fails immediately (see *Behaviour without the platform* below). Deployment guides and API documentation: [AGENTIC STAR Developers](https://developers.fd.agenticstar.tm.softbank.jp/) |
| **AgentCore Framework** (`agenticstar-agentcore`) | Installed from PyPI as a dependency. |
| Python | >=3.11 |

```bash
pip install -e .
```

### Behaviour without the platform

The framework is designed to run **only** on AGENTIC STAR. There is no fallback or degraded
mode. If the platform is unreachable or the SDK version does not match, the agent raises
`PlatformRequired` during graph compile / start-up preflight rather than starting in a partially
working state. This is intentional — a half-running agent is worse than one that refuses to start.

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Tests run without a platform connection. Running the agent itself does not.

## Project Structure

```
src/          agent implementation (nodes, services, schemas)
tests/        unit, integration and boundary tests
config/       agent configuration
docs/         design and operational documentation
```

See `docs/` for the design spec and test specification.

## Customising

1. Adjust `config/` for your own environment and policies.
2. Replace the knowledge sources and sample data with your own.
3. Review the node implementations under `src/nodes/` for domain-specific logic.
4. Re-run the test suite.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This template is published **as is**, by its individual author, under the MIT license. It carries
**no warranty and no support commitment**, and no organisation stands behind its behaviour or
fitness for any purpose. Issues and pull requests may or may not receive a response; that is at
the sole discretion of the repository owner.
