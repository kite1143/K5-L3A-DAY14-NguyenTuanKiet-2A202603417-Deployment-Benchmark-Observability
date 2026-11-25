# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong source code (`develop/app.py` dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - **Cách `production/` đã sửa:** `01-localhost-vs-production/production/config.py` đọc qua `os.getenv("OPENAI_API_KEY", "")` (dòng 27) và `os.getenv("AGENT_API_KEY", "")` (dòng 32), dùng `.env.example` làm mẫu và ignore `.env` trong `.gitignore`.
2. **Không có config management tập trung (`develop/app.py` dòng 21–22):**
   - `DEBUG = True`, `MAX_TOKENS = 500` viết cứng trong `app.py`, không đổi được theo từng môi trường (dev/staging/prod).
   - **Cách `production/` đã sửa:** `production/config.py` gom vào dataclass `Settings` đọc từ biến môi trường và kiểm tra hợp lệ bằng `validate()` (dòng 15–50).
3. **Dùng `print()` và lộ secret ra log (`develop/app.py` dòng 33–34, 38):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` in thẳng API key ra stdout; log text tự do khó parse.
   - **Cách `production/` đã sửa:** `production/app.py` cấu hình `logging` định dạng JSON (dòng 28–31) và chỉ log metadata như `question_length`, `client_ip` (dòng 111–115), tuyệt đối không log secret.
4. **Thiếu health check và readiness endpoint (`develop/app.py` dòng 42–43):**
   - Không có `/health` hay `/ready`, nên cloud platform/load balancer không biết khi nào container chết hoặc chưa sẵn sàng nhận traffic.
   - **Cách `production/` đã sửa:** `production/app.py` bổ sung `GET /health` (dòng 135–149) và `GET /ready` (dòng 152–161).
5. **Bind `localhost`, cứng `port=8000` và bật `reload=True` (`develop/app.py` dòng 49–54):**
   - `host="localhost"` chỉ nghe nội bộ máy (trong container Docker sẽ không truy cập được từ ngoài); `port=8000` bỏ qua biến `PORT` do Railway/Render cấp; `reload=True` tốn tài nguyên và không an toàn ở production.
   - **Cách `production/` đã sửa:** `production/app.py` dùng `host=settings.host` (mặc định `0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug` (dòng 194–199).
6. **Không xử lý graceful shutdown:**
   - Khi nhận `SIGTERM` lúc deploy lại hoặc scale down, process tắt ngang làm đứt request đang xử lý.
   - **Cách `production/` đã sửa:** `production/app.py` dùng `lifespan` (dòng 39–67) để hạ `is_ready = False` trước khi tắt và đăng ký `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 180–189).

---

### Exercise 1.2: Kết quả chạy bản `develop`

Lệnh chạy:
```bash
curl -i -s -X POST "http://localhost:8000/ask?question=Hello"
```

Output thực tế:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:03:44 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Kết quả test bản `production` (`/health`, `/ready`, `POST /ask`):
```json
GET /health -> {"status":"ok","uptime_seconds":0.7,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:03:47.313917+00:00"}
GET /ready  -> {"ready":true}
POST /ask   -> {"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}
```

---

### Exercise 1.3: Bảng so sánh Develop vs Production

| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config & Secrets | Hardcode trực tiếp trong `app.py` (`OPENAI_API_KEY`, `PORT=8000`, `DEBUG=True`) | Đọc từ biến môi trường qua `Settings` (`config.py`), validate khi khởi động | Tránh lộ secret khi push Git; đổi cấu hình giữa dev/staging/prod không cần sửa code. |
| Health check | Không có endpoint kiểm tra sức khỏe | Có `GET /health` (liveness) và `GET /ready` (readiness, trả 503 nếu chưa sẵn sàng) | Platform/load balancer tự động restart khi app treo và không route traffic vào instance chưa sẵn sàng. |
| Logging | Dùng `print()` text thuần, in cả API key ra stdout | `logging` có cấu trúc JSON, không log dữ liệu nhạy cảm | Dễ gom và truy vấn log trên hệ thống tập trung (Loki, Datadog), đảm bảo an toàn thông tin. |
| Shutdown | Tắt đột ngột khi process dừng | Dùng `lifespan` + bắt `SIGTERM` để hoàn thành request đang chạy rồi mới thoát | Tránh rớt request của người dùng (502/504) khi rolling deploy hoặc scale down. |
| Network & Reload | Bind `localhost:8000`, luôn bật `reload=True` | Bind `0.0.0.0`, đọc `PORT` từ env, `reload` chỉ bật khi `DEBUG=true` | Container/cloud bắt buộc listen trên `0.0.0.0` và cổng `PORT` được cấp; tắt `reload` để ổn định hiệu năng. |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image là gì?** `python:3.11` (bản Python đầy đủ, nặng ~1 GB).
2. **Working directory là gì?** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` trước?** Để tận dụng Docker layer cache: khi chỉ sửa code (`app.py`) mà `requirements.txt` không đổi, Docker tái sử dụng lại layer `pip install` đã cache thay vì tải và cài lại toàn bộ dependencies.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?** `ENTRYPOINT` cố định executable chính khi container chạy (không bị ghi đè bởi tham số cuối lệnh `docker run`), còn `CMD` chỉ định lệnh/tham số mặc định và dễ bị ghi đè khi truyền thêm command lúc chạy `docker run <image> <command>`.

### Exercise 2.2: Build và chạy `my-agent:develop`

Build từ gốc repo:
```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d -p 8000:8000 my-agent:develop
curl -i -s -X POST "http://localhost:8000/ask?question=What%20is%20Docker?"
```

Kết quả thực tế:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:09:39 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build & so sánh kích thước

- **Stage 1 (`builder` từ `python:3.11-slim`):** Cài build tools (`gcc`, `libpq-dev`) và cài dependencies bằng `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
- **Stage 2 (`runtime` từ `python:3.11-slim`):** Tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local` cùng `main.py` và `utils/mock_llm.py`, loại bỏ hoàn toàn `gcc`, `libpq-dev` và cache cài đặt.
- **Kích thước đo bằng `docker images my-agent`:**
  - `my-agent:develop`: **1.67GB** (~1670 MB)
  - `my-agent:advanced`: **240MB**
  - **Chênh lệch:** Giảm **85.6%** (`(1670 - 240) / 1670`, nhỏ hơn ~6.96 lần).

### Exercise 2.4: Docker Compose stack (`02-docker/production/`)

Sơ đồ kiến trúc các service trong network `internal`:
```text
Client (HTTP :80)
   │
   ▼
[ nginx ] (nginx:alpine, expose 80:80, 443:443)
   │  proxy_pass
   ▼
[ agent ] (my-agent runtime, port 8000 nội bộ, depends_on redis & qdrant healthy)
   ├──► [ redis ]  (redis:7-alpine, 6379, volume: redis_data)
   └──► [ qdrant ] (qdrant/qdrant:v1.9.0, 6333, volume: qdrant_data)
```

Kết quả test qua Nginx (`docker compose -p k5-day14-docker up -d --build`):
```json
GET http://localhost/health
-> {"status":"ok","uptime_seconds":0.9,"version":"2.0.0","timestamp":"2026-11-25T09:12:13.640707"}

POST http://localhost/ask  (-d '{"question": "Explain microservices"}')
-> {"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 (`06-lab-complete/`)

- **Platform:** Render (Web Service `Docker` + Key Value Redis)
- **Public URL:** https://k5-l3a-day14-nguyentuankiet-2a202603417.onrender.com
- **Kết quả 4 lệnh tự kiểm CP6:**
  - `GET /health` → `200` (`{"status":"ok","environment":"production"}`)
  - `GET /ready` → `200` (`{"ready":true}`)
  - `POST /ask` (không key) → `401`
  - `POST /ask` (có `X-API-Key`) → `200` (`{"question":"Hello","answer":"...","cost_usd":2.07e-05}`)
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` (chi tiết xem [DEPLOYMENT.md](DEPLOYMENT.md))

### So sánh `railway.toml` và `render.yaml`

| Tiêu chí | `railway.toml` | `render.yaml` |
|----------|----------------|---------------|
| Định dạng & phạm vi | TOML — cấu hình cho **1 service** hiện tại | YAML (Blueprint IaC) — khai báo được **nhiều service/database** cùng lúc trong `services:` |
| Cách build | `[build] builder = "DOCKERFILE"` | `runtime: docker` trong từng service |
| Health check | `[deploy] healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Biến môi trường & Secret | Không khai báo secret trong file; set riêng qua Dashboard hoặc `railway variables set` | Khai báo `envVars` ngay trong YAML; secret dùng `generateValue: true` (tự sinh) hoặc `sync: false` (nhập trên Dashboard) |
| Lý do khác nhau | Railway ưu tiên cấu hình tối giản theo từng service, quản lý env/plugin (Redis) tách biệt trên Dashboard/CLI | Render dùng Blueprint để dựng toàn bộ stack (web + env + DB/Redis) lặp lại được từ 1 file Git |

### Exercise 3.3: Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

- `cloudbuild.yaml` định nghĩa pipeline 4 bước chạy tuần tự (`waitFor`) khi có trigger push lên `main`:
  1. **`test`** (`python:3.11-slim`): cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`.
  2. **`build`** (`gcr.io/cloud-builders/docker`): build Docker image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from` từ image `latest`).
  3. **`push`**: đẩy cả 2 tag lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
  4. **`deploy`** (`gcloud run deploy`): triển khai bản `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình autoscale (`min=1`, `max=10`), `512Mi` RAM / `1` CPU, và inject secret từ Secret Manager (`--set-secrets`).
- `service.yaml` là file IaC chuẩn Knative (`serving.knative.dev/v1`) mô tả cấu hình runtime tương ứng: `containerConcurrency: 80`, `livenessProbe` (`/health`), `startupProbe` (`/ready`), và lấy `OPENAI_API_KEY` / `AGENT_API_KEY` từ Secret Manager (`secretKeyRef`).

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/`)

1. **Không có API key (→ `401 Unauthorized`):**
```bash
curl -i -s -X POST -H "Content-Type: application/json" -d '{"question":"hello"}' http://localhost:8000/ask
```
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 09:22:38 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

2. **Có API key hợp lệ (→ `200 OK`):**
```bash
curl -i -s -H "X-API-Key: secret-key-123" -X POST -H "Content-Type: application/json" -d '{"question":"hello"}' http://localhost:8000/ask
```
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:22:38 GMT
server: uvicorn
content-length: 114
content-type: application/json

{"question":"hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

1. **Lấy JWT token (`POST /auth/token` với `student` / `demo123`) và gọi request đầu tiên (→ `200 OK`):**
```bash
curl -i -s -H "Authorization: Bearer <REDACTED_TOKEN>" -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" -d '{"question":"what is docker?"}'
```
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 09:22:40 GMT
server: uvicorn
content-length: 196
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"what is docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

2. **Vòng lặp gọi liên tiếp vượt 10 req/phút (request 2–10 → `200`, request 11 → `429 Too Many Requests`):**
```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 09:22:41 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795598622
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

### Exercise 4.4: Cách làm Cost Guard (`04-api-gateway/production/cost_guard.py`)

- **Phân biệt với Rate Limit:** Rate limit giới hạn **tốc độ** (số request/phút để chống spam/DDoS), còn Cost Guard giới hạn **chi phí tiền** theo ngày (tránh một user gửi prompt rất dài hoặc gọi đều đặn cả ngày gây vượt ngân sách LLM). Cần cả hai vì request hợp lệ dưới ngưỡng rate limit vẫn có thể đốt hết tiền nếu token lớn.
- **Cơ chế hoạt động trong `CostGuard`:**
  1. **Trước khi gọi LLM (`check_budget(username)`):** Kiểm tra tổng chi phí toàn hệ thống (`_global_cost >= global_daily_budget_usd` = `$10/ngày` → trả `503`) và chi phí trong ngày của user (`record.total_cost_usd >= daily_budget_usd` = `$1/ngày` → trả `402 Payment Required`). Nếu đạt `80%` (`warn_at_pct = 0.8`) thì ghi log cảnh báo.
  2. **Sau khi gọi LLM (`record_usage(username, input_tokens, output_tokens)`):** Cộng dồn token input/output và tính tiền theo đơn giá (`$0.00015 / 1K input`, `$0.0006 / 1K output`), cập nhật cả record của user và `_global_cost`. Trong production thực tế (như Part 6), bộ đếm này phải lưu trong **Redis** thay vì RAM để không mất khi restart hoặc chạy nhiều instance.

## Part 5: Scaling & Reliability

### Exercise 5.1–5.3: Health Check & Graceful Shutdown (`05-scaling-reliability/develop/`)

1. **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
   - `GET /health` (**Liveness probe**): Kiểm tra process còn sống không (trả `200` kèm uptime, memory). Nếu fail → platform restart container.
   - `GET /ready` (**Readiness probe**): Kiểm tra agent đã sẵn sàng nhận traffic mới chưa (trả `503` khi đang khởi động, đang shutdown, hoặc dependency như Redis chưa sẵn sàng). Nếu fail → load balancer ngừng route request mới tới instance đó, nhưng không restart container.
   - Kết quả đo thực tế:
     ```json
     GET /health -> {"status":"ok","uptime_seconds":0.3,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T09:25:42.340325+00:00","checks":{"memory":{"status":"ok","used_percent":11.0}}}
     GET /ready  -> {"ready":true,"in_flight_requests":1}
     ```

2. **Graceful Shutdown khi nhận `SIGTERM`:**
   - Gửi 2 request `POST /ask` song song rồi gửi `kill -SIGTERM` sau 0.5 giây.
   - Kết quả: Cả 2 request đang chạy vẫn hoàn thành và trả **`HTTP 200`**, sau đó server mới ghi log `Graceful shutdown initiated...` → `Shutdown complete` và thoát an toàn.

### Exercise 5.4–5.5: Stateless Agent + Redis + Nginx (`05-scaling-reliability/production/`)

- **Tại sao state trong RAM hỏng khi scale nhiều instance?** Nếu lưu lịch sử hội thoại trong RAM của từng process, Nginx load balancer (round-robin) sẽ gửi request 1 tới `instance-A` và request 2 tới `instance-B`, làm `instance-B` không thấy lịch sử của session đó.
- **Giải pháp Stateless:** Đưa toàn bộ session history ra **Redis** dùng chung cho cả 3 replica.
- **Kết quả chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py`:**
  ```text
  Session ID: 1d7d62e9-f698-431b-8cc5-15c1c3db3ccb
  Request 1: [instance-3208ec]
  Request 2: [instance-40273b]
  Request 3: [instance-689afc]
  Request 4: [instance-3208ec]
  Request 5: [instance-40273b]

  Total requests: 5
  Instances used: {'instance-40273b', 'instance-689afc', 'instance-3208ec'}
  ✅ All requests served despite different instances!

  --- Conversation History ---
  Total messages: 10
  ✅ Session history preserved across all instances via Redis!
  ```
  Nginx phân phối đều 5 request qua cả 3 instance (`instance-3208ec`, `instance-40273b`, `instance-689afc`), nhưng `GET /chat/{session_id}/history` vẫn đọc đủ 10 message (5 user + 5 assistant) từ Redis.

## Part 6: Final Project (`check_production_ready.py`)

Chạy `python check_production_ready.py` trong `06-lab-complete/` (WSL2 + Docker):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

- Kích thước Docker image thực tế: **238 MB** (< 500 MB).
- `docker stop` thoát êm với exit code `0` trong **0.5s**.

---

## AI log

- **CP1:** Dùng AI hỗ trợ đối chiếu các anti-pattern giữa `01-localhost-vs-production/develop/app.py` và `production/app.py`, chạy kiểm thử cả hai app trong WSL2 để lấy output thực tế và tổng hợp câu trả lời vào `MISSION_ANSWERS.md`.
- **CP2:** Dùng AI hỗ trợ chạy build `my-agent:develop` và `my-agent:advanced`, test Docker Compose stack qua Nginx trong WSL2 và ghi lại số đo kích thước image cùng câu trả lời Part 2 vào `MISSION_ANSWERS.md`.
- **CP3:** Dùng AI hỗ trợ chạy test API Key (401/200), lấy JWT token `student/demo123`, chạy vòng lặp kiểm tra rate limit (429) trong WSL2 và tổng hợp giải thích Cost Guard vào `MISSION_ANSWERS.md`.
- **CP4:** Dùng AI hỗ trợ chạy test `/health`, `/ready`, graceful shutdown (2 in-flight request + `SIGTERM`) ở bản develop, chạy stack 3 replicas + Redis + Nginx với `test_stateless.py` trong WSL2 và ghi kết quả vào `MISSION_ANSWERS.md`.
- **CP5:** Dùng AI hỗ trợ hoàn thiện các file TODO trong `06-lab-complete/` (`app/`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) và chạy `python check_production_ready.py` trong WSL2 đạt `PASS 12/12` (`43/43 checks passed`).
- **CP6:** Dùng AI hỗ trợ kiểm tra 4 endpoint trên URL Render đã deploy (`/health`, `/ready`, `/ask` 401/200), viết `DEPLOYMENT.md` và hoàn thiện mục Part 3 (so sánh `railway.toml` vs `render.yaml`, mô tả pipeline Cloud Run) trong `MISSION_ANSWERS.md`.
