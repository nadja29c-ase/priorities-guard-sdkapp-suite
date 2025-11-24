#!/bin/bash

# Exchange authorization code for tokens
curl -X POST http://localhost:8000/oauth/focused/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "authorization_code",
    "code": "nq0g0RsUBAcn3DxM8TlgZl4KV0RMQLMj34i2YKfrOxgbEObG9c4lk0ab5pGRqyZz0iHaiZqqHOk9kx1dIHfbc__KMFXB3sK5vNpy3BV2xuBzzYillRf2y556PCnlim46",
    "code_verifier": "q5gAfnxvpA7j7X49CT4tlojAxCqV__BFqSb64QT2zA8",
    "client_id": "focused-client-ff142fb8-19a6-4d48-b6b7-f4032974443d",
    "redirect_uri": "https://chatgpt.com/aip/callback"
  }'
