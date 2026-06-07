# Morae Model Fitness Platform (MMFP)

Morae's AI products need to make recurring decisions about which model to use for which job. Today these decisions are made ad-hoc per product team, captured in slides or deeply embedded into code, and not re-validated. The Morae Model Fitness Platform addresses this by providing a shared, opinionated internal platform for evaluating model fitness — a versioned rubric, reproducible evaluation harness, and lightweight UI — letting product teams make model selection decisions that are evidence-based, comparable across products, and durable, with less effort per decision than ad-hoc evaluation provides today. MMFP is an assessment tool, not a deployment tool: it produces scorecards that humans use to decide which models to designate as primary or fallback for a given AI product; consuming products read those recommendations and update their own configuration.

## Links

- Jira epic: [MLI-104](https://morae.atlassian.net/browse/MLI-104)
- Confluence: [Model Fitness Platform](https://morae.atlassian.net/wiki/spaces/MMFP/overview)
- Agent guidance: [CLAUDE.md](CLAUDE.md)

## Dev quickstart

```bash
# Clone
git clone https://github.com/morae-product-engineering/model-fitness.git
cd model-fitness

# Python (backend)
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Node (frontend + tests)
npm install

# Run end-to-end tests
npx playwright test

# Run Python tests
pytest
```

**Running Playwright locally.** Tests against the deployed dev environment require basic-auth credentials. Export `MMFP_BASIC_AUTH_USER` and `MMFP_BASIC_AUTH_PASS` from 1Password ("MMFP / dev UI basic auth") before running `npx playwright test`. These will be removed when Entra SSO replaces basic auth.
