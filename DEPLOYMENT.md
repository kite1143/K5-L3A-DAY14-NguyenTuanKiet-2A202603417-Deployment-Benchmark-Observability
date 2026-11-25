# Deployment Information

## Public URL
https://k5-l3a-day14-nguyentuankiet-2a202603417.onrender.com

## Platform
Render (Web Service `Docker` từ `06-lab-complete/` + Render Key Value Redis)

## Test Commands

### Health & Readiness Check
```bash
curl https://k5-l3a-day14-nguyentuankiet-2a202603417.onrender.com/health
# Expected: {"status":"ok","environment":"production"}

curl https://k5-l3a-day14-nguyentuankiet-2a202603417.onrender.com/ready
# Expected: {"ready":true}
```

### API Test (authentication)
```bash
# Không có key -> 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST \
  https://k5-l3a-day14-nguyentuankiet-2a202603417.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'

# Có X-API-Key -> 200
curl -X POST https://k5-l3a-day14-nguyentuankiet-2a202603417.onrender.com/ask \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
```

## Environment Variables Set (trên Render Dashboard)
- `REDIS_URL` (Internal Key Value URL)
- `AGENT_API_KEY` (đặt trực tiếp trên Render, không commit vào Git)
- `ENVIRONMENT=production`
- `RATE_LIMIT_PER_MINUTE=10`
- `DAILY_BUDGET_USD=1.0`
- `MONTHLY_BUDGET_USD=10.0`

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
