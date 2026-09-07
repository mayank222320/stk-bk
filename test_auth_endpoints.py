from fastapi.testclient import TestClient
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import app
from core.config import settings

client = TestClient(app)
API_TOKEN = settings().api_token

response = client.get("/performance/hit-rate")
print(f"Without token: {response.status_code}")

response = client.get("/performance/hit-rate", headers={"X-API-Token": API_TOKEN})
print(f"With correct token: {response.status_code}")

response = client.get("/performance/hit-rate", headers={"X-API-Token": "wrongtoken"})
print(f"With wrong token: {response.status_code}")

response = client.get("/")
print(f"System endpoint without token: {response.status_code}")

response = client.delete("/portfolio/positions/all", headers={"X-API-Token": API_TOKEN})
print(f"Cleanup endpoint response: {response.json()}")
