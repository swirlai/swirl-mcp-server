# Template Gitflow Repository

This repository serves as a template for Gitflow-based repositories. It includes predefined workflows, actions, and templates to streamline the development process.

## Repository Structure

- `.github/`
    - `workflows/`: Contains GitHub Actions workflows.
    - `PULL_REQUEST_TEMPLATE.md`: Template for pull requests.
    - `ISSUE_TEMPLATE/`: Templates for issues.
- `src/`: Source code directory.
- `tests/`: Test code directory.

## Gitflow Workflow

This repository follows the Gitflow branching model:
- `main`: The production-ready branch.
- `develop`: The branch for ongoing development.
- `feature/*`: Branches for new features.
- `bugfix/*`: Branches for bug fixes.
- `release_#_#_#`: Older style for branches for preparing a new release.
- `v#_#_#_#`: New Style for release stabilization branches

We do not enforce the feature, bugfix naming convention, but it is recommended to follow it.

## GitHub Actions Workflows

### Check Spelling

This workflow checks for spelling errors in the `docs/` directory and runs on changes to the `main` branch or pull requests to `develop` and `main`.

```yaml
name: Check Spelling

on:
  push:
    branches:
      - "main"
    paths:
      - "docs/**"
  pull_request:
    branches:
      - develop
      - main
    paths-ignore:
      - '.github/**'
      - 'integrations/**'
      - 'swirl-infra/**'
      - 'db.sqlite3.dist'
  workflow_dispatch:

permissions:
  contents: read
  actions: read
  checks: write
  pull-requests: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check Spelling
        uses: crate-ci/typos@master
        with:
          config: ./.github/workflows/typos.toml
          write_changes: true