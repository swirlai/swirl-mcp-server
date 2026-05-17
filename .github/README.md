# Github Actions and Workflows

We have three basic types of objects in our actions and workflows directories
* action - resuable logic consumed by workflows
* reusable workflow - a workflow that can be consumed by other workflows
* workflow - a workflow that is run on a schedule or in response to an event (equivalent to a pipeline in Jenkins)


# Testing locally
1. Install the act `brew install act`
2. Run to test

E.g., 
```bash
act -W .github/workflows/reusable-rotate-pods-nonprod-swirl.yml --input cluster_env=prf
```