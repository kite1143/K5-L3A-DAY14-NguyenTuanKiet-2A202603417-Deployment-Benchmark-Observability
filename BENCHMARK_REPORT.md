# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** NguyenTuanKiet - 2A202603417
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows + WSL2 Ubuntu (Python 3.14.4), Docker Desktop 29.9.3

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 95% người dùng nhận phản hồi dưới 0.5s (tránh cảm giác giật lag), phù hợp mặc định của `load_test.py`. |
| Error rate `/ask` | < 2.0 % | Chịu được ~1% lỗi upstream ngẫu nhiên (`MOCK_ERROR_RATE=0.01`), tránh báo động giả khi spike ngắn. |
| Accuracy trên golden dataset | ≥ 80 % | Đảm bảo chất lượng trả lời đạt chuẩn tối thiểu và không có regression so với baseline trước khi deploy. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.45 | 190.8 | 219.5 | 1702.7 | 1.00% | PASS |
| 10 | 36.92 | 187.6 | 221.9 | 1695.3 | 0.67% | PASS |
| 50 | 121.89 | 195.6 | 245.1 | 1657.3 | 0.67% | PASS |
| 100 | 132.55 | 206.2 | 317.5 | 1695.2 | 1.33% | PASS |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không tăng tuyến tính ở mức cao: từ `c=1` → `c=10` RPS tăng ~8.3x (`4.45` → `36.92`), `c=10` → `c=50` tăng ~3.3x (`36.92` → `121.89`), nhưng `c=50` → `c=100` chỉ tăng nhẹ lên `132.55 req/s` trong khi `p95` tăng từ `245.1 ms` lên `317.5 ms`. Nguyên nhân là chỉ có 1 process uvicorn (1 CPU event loop) nên khi concurrency vượt điểm bão hòa, request phải xếp hàng chờ xử lý.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 189.7 | 218.2 | 233.2 |
| 0.03 (mặc định) | 230.5 | 224.0 | 1690.3 |
| 0.1 | 325.3 | 1690.4 | 1716.5 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p99` (và `p95` khi tỉ lệ chậm ≥ 5–10%) nhạy nhất: ở `MOCK_SLOW_RATE=0.03`, `avg` chỉ tăng nhẹ từ `189.7 ms` lên `230.5 ms` nhưng `p99` nhảy vọt từ `233.2 ms` lên `1690.3 ms` (~7.2x). Khi `MOCK_SLOW_RATE=0.1`, `p95` nhảy lên `1690.4 ms` làm SLO p95 ≤ 500ms FAIL. Đặt SLO theo average sẽ che giấu nhóm người dùng đang phải chờ gần 2 giây.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.3 | 109.1 | 112.0 |
| Tổng cost (USD) | $0.000393 | $0.000762 | $0.000776 |
| Cost / câu đúng (USD) | $0.00039315 | $0.00003627 | $0.00003374 |
| Quality gate | FAIL | PASS | PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "api key"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["kubernetes", "hpa"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`). |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2 (và CI quality gate):**

- Agent v2 tốn gần gấp đôi token mỗi câu (`109.1–112.0` vs `56.3`) và `p95` cao hơn ~47 ms (`225.8 ms` vs `178.3 ms`) do thêm bước retrieval, nhưng accuracy tăng từ `4.3%` lên `100.0%` và **cost / câu đúng** giảm hơn **11 lần** (`$0.00003374` vs `$0.00039315`).
- **CI Quality Gate:** Khi chạy `python eval/run_eval.py --url http://localhost:8001 --baseline reports/eval_v2.json`, script phát hiện 20 câu regression và trả về **exit code `1`** (`❌ FAIL`). Trong GitHub Actions, chỉ cần thêm step chạy lệnh eval này trên PR: nếu accuracy dưới ngưỡng hoặc có regression, exit code `1` sẽ tự động fail job và chặn merge:
  ```yaml
  - name: Eval Quality Gate
    run: python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json
  ```

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] `screenshots/grafana-dashboard.png` — Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [x] `screenshots/jaeger-slow-trace.png` — Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [x] `screenshots/jaeger-error-trace.png` — Một trace lỗi trong Jaeger (có event `exception`)
- [x] `screenshots/prometheus-alert-firing.png` — Trang Alerts của Prometheus với ≥ 2 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~88s (`pending` ở 27s, `for: 1m`) | Golden Signals — Error rate & `llm_calls` error |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | ~147s (`pending` ở 27s, `for: 2m`) | Golden Signals — p95 & Latency & Traffic (p95/p99) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | ~17s (kèm tải trước đó, `for: 2m`) | LLM — Cost USD/giờ & LLM p95 |
| D | `docker pause` 1 instance | `AgentInstanceDown` (theo rule) | Chưa chạy riêng (`for: 30s` theo `alert_rules.yml`) | Golden Signals — Instances up & Nginx 504 |
| E | `AGENT_VERSION=v1` | Không có alert nào | Không firing | LLM — Retrieval hit ratio & bảng Version |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Alert hạ tầng chỉ đo 4 Golden Signals (latency, traffic, error, saturation) và chi phí, không đo **độ đúng của câu trả lời**. Để phát hiện suy giảm chất lượng trong production cần: (1) chạy `eval/run_eval.py` trên golden dataset trong CI trước khi deploy để chặn regression, (2) theo dõi metric nghiệp vụ như *retrieval hit ratio* hoặc *user thumbs-down / feedback rate*, và (3) lấy mẫu log/trace định kỳ để chấm bằng LLM-as-judge.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong log/Jaeger:

- `trace_id`: `569fa6b295b56552a0c8c3c26c6de1c8`
- Tổng thời gian: `1721.9 ms`
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1696.1 ms`, `98.5%` tổng thời gian)
- Dòng log tương ứng (lấy từ `docker compose -p k5-day14-observability logs agent`):

```json
{"ts": "2026-11-25T10:36:48.575637+00:00", "level": "INFO", "service": "observable-agent", "instance": "cb0b41681014", "event": "http_request", "trace_id": "569fa6b295b56552a0c8c3c26c6de1c8", "span_id": "d938d8b2d34ddbed", "request_id": "550dcc07a7d7", "method": "POST", "route": "/ask", "status": 200, "ms": 1721.9}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 65.94 | 190 | 220 | 1700 | 75 (0.95% / 7890 reqs) |
| 3 | 65.67 | 190 | 230 | 1700 | 64 (0.81% / 7867 reqs) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance **không cải thiện p95 (`220 ms` → `230 ms`) lẫn RPS (`65.94` → `65.67`)**. Nguyên nhân: (1) ở mức 100 user có `wait_time` trong Locust, tải phát ra chỉ ~66 req/s nên 1 instance FastAPI/uvicorn async chưa bị bão hòa CPU; (2) nút thắt của độ trễ p95/p99 nằm ở **thời gian chờ upstream LLM** (`MOCK_LATENCY_MS` + 3% tail latency ~`1700 ms`), không phải ở CPU hay số lượng replica của agent.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. Không dùng latency trung bình làm SLO: `avg` che giấu tail latency (`p99` nhảy lên ~`1700 ms` khi chỉ có 3% request chậm).
  2. Eval trên golden dataset + quality gate trong CI giúp bắt regression chất lượng mà alert hạ tầng (4 Golden Signals) không thấy được.
  3. Kết hợp Metrics (Prometheus/Grafana) → Traces (OpenTelemetry/Jaeger) → JSON Logs qua `trace_id` giúp khoanh vùng nhanh nguyên nhân chậm/lỗi thuộc về LLM upstream hay code ứng dụng.
- Nếu đưa agent này lên production thật, sẽ thêm metric / alert:
  1. Metric tỷ lệ fallback / empty retrieval và điểm đánh giá chất lượng mẫu (online eval / user feedback score).
  2. Alert hết quota / tỷ lệ `429` và `402` theo từng client, cộng với synthetic health probe từ bên ngoài load balancer (để bắt lỗi `502`/`504` ở tầng Nginx/CDN).
