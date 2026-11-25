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

_(Chưa thực hiện — CP6)_

## Part 4: API Security

_(Chưa thực hiện — CP3)_

## Part 5: Scaling & Reliability

_(Chưa thực hiện — CP4)_

## Part 6: Final Project (`check_production_ready.py`)

_(Chưa thực hiện — CP5)_

---

## AI log

- **CP1:** Dùng AI hỗ trợ đối chiếu các anti-pattern giữa `01-localhost-vs-production/develop/app.py` và `production/app.py`, chạy kiểm thử cả hai app trong WSL2 để lấy output thực tế và tổng hợp câu trả lời vào `MISSION_ANSWERS.md`.
- **CP2:** Dùng AI hỗ trợ chạy build `my-agent:develop` và `my-agent:advanced`, test Docker Compose stack qua Nginx trong WSL2 và ghi lại số đo kích thước image cùng câu trả lời Part 2 vào `MISSION_ANSWERS.md`.
