curl -X POST http://localhost:8000/oauth/focused/register \
  -H "Content-Type: application/json" \
  -d '{"client_name":"Test Client","redirect_uris":["https://chatgpt.com/aip/callback"]}'
