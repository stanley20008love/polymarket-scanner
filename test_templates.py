#!/usr/bin/env python3
import requests, json

ZEABUR_TOKEN = "sk-y25egzkiyfogzhzkmypflc5ch5m2w"
PROJECT_ID = "69e85db920af06d5e82f51e1"

templates = [
    # Try 1: source directly with git keys
    """apiVersion: zeabur.com/v1
kind: Template
metadata:
  name: Polymarket Scanner
spec:
  services:
    - name: polymarket-scanner
      template: GIT
      spec:
        source:
          type: GITHUB
          repoID: "1217956087"
          branch: main
        ports:
          - id: web
            port: 8501
            type: HTTP
""",
    # Try 2: git at top level of spec  
    """apiVersion: zeabur.com/v1
kind: Template
metadata:
  name: Polymarket Scanner
spec:
  services:
    - name: polymarket-scanner
      template: GIT
      spec:
        git:
          type: GITHUB
          repoID: "1217956087"
          branch: main
        ports:
          - id: web
            port: 8501
            type: HTTP
""",
    # Try 3: source.git with different key names
    """apiVersion: zeabur.com/v1
kind: Template
metadata:
  name: Polymarket Scanner
spec:
  services:
    - name: polymarket-scanner
      template: GIT
      spec:
        source:
          git:
            provider: GITHUB
            repositoryId: "1217956087"
            branch: main
        ports:
          - id: web
            port: 8501
            type: HTTP
""",
    # Try 4: prebuilt with custom Docker image approach
    """apiVersion: zeabur.com/v1
kind: Template
metadata:
  name: Polymarket Scanner
spec:
  services:
    - name: polymarket-scanner
      template: GIT
      spec:
        source:
          git:
            type: github
            repoID: "1217956087"
            branch: main
        ports:
          - id: web
            port: 8501
            type: HTTP
""",
]

for i, template in enumerate(templates):
    result = requests.post(
        "https://api.zeabur.com/graphql",
        headers={"Authorization": f"Bearer {ZEABUR_TOKEN}", "Content-Type": "application/json"},
        json={
            "query": """mutation DeployTemplate($rawSpecYaml: String, $projectId: ObjectID) {
                deployTemplate(rawSpecYaml: $rawSpecYaml, projectID: $projectId) { _id }
            }""",
            "variables": {"rawSpecYaml": template, "projectId": PROJECT_ID}
        }
    ).json()
    
    errors = result.get("errors", [])
    if errors:
        desc = errors[0].get("extensions", {}).get("description", errors[0].get("message", ""))
        print(f"Try {i+1}: {desc[:150]}")
    else:
        print(f"Try {i+1}: SUCCESS! {json.dumps(result)}")
