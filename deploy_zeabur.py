#!/usr/bin/env python3
"""Deploy Polymarket Scanner to Zeabur"""
import requests, json, time

ZEABUR_TOKEN = "sk-y25egzkiyfogzhzkmypflc5ch5m2w"
PROJECT_ID = "69e9698e6144d0e403730867"

def graphql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    response = requests.post(
        "https://api.zeabur.com/graphql",
        headers={"Authorization": f"Bearer {ZEABUR_TOKEN}", "Content-Type": "application/json"},
        json=payload
    )
    return response.json()

# Template YAML - GIT service from GitHub
TEMPLATE_YAML = """apiVersion: zeabur.com/v1
kind: Template
metadata:
  name: Polymarket Scanner
spec:
  description: Polymarket Arbitrage Scanner with Options Vol Surface
  variables:
    - key: PUBLIC_DOMAIN
      type: DOMAIN
      name: Domain
      description: Domain for the Polymarket Scanner dashboard
  services:
    - name: polymarket-scanner
      template: GIT
      domainKey: PUBLIC_DOMAIN
      spec:
        source:
          source: GITHUB
          repo: "1217956087"
          branch: main
          rootDirectory: .
        ports:
          - id: web
            port: 8501
            type: HTTP
        env:
          PORT:
            default: "8501"
"""

# Deploy using template
print("=== Deploying via Template API ===")
result = graphql("""
mutation DeployTemplate($rawSpecYaml: String, $projectId: ObjectID) {
  deployTemplate(rawSpecYaml: $rawSpecYaml, projectID: $projectId) {
    _id
  }
}
""", {"rawSpecYaml": TEMPLATE_YAML, "projectId": PROJECT_ID})
print(json.dumps(result, indent=2))

# Wait a moment for deployment to start
time.sleep(3)

# Check project services
print("\n=== Current Project Services ===")
result = graphql('{ project(_id: "%s") { _id name services { _id name status domains { _id domain } } } }' % PROJECT_ID)
print(json.dumps(result, indent=2))

# Get environments
print("\n=== Environments ===")
result = graphql('{ project(_id: "%s") { environments { _id name } } }' % PROJECT_ID)
print(json.dumps(result, indent=2))
