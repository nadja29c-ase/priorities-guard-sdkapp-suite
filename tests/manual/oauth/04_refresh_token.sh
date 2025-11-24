#!/bin/bash

# Test token refresh
curl -X POST http://localhost:8000/oauth/focused/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "refresh_token",
    "refresh_token": "lwjiTFFfcuaE7g6ZlHUOTrO09Rqa50zPHYlkHX4qXYQ",
    "client_id": "focused-client-ff142fb8-19a6-4d48-b6b7-f4032974443d"
  }'
