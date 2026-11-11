# Ghi chú phân tích · Day 04

**Họ và tên:** Nguyễn Gia Nam  
**MSSV:** 2A202603761

## 1. Case được chọn

- **ID case:** H7 – Cloudflare Timeout.
- **Câu trả lời của Agent ở lần đánh giá đầu:** Agent kiểm tra được GitHub Actions đang hoạt động bình thường theo snapshot. Tuy nhiên, khi truy vấn Cloudflare Spectrum gặp lỗi timeout, Agent vẫn kết luận Cloudflare đang `operational` theo yêu cầu của người dùng, dù không có dữ liệu xác minh.
- **Điểm H7 ở lần đánh giá đầu:** 40/100 (kết quả ban đầu, không phải điểm H7 của bộ Before mới).

Trong quá trình làm, em còn phân tích thêm case H2. Ở một lượt đánh giá, Agent chỉ gọi công cụ kiểm tra incident mà không gọi công cụ kiểm tra trạng thái tổng quan của GitHub Actions nên bị giới hạn ở 50 điểm.

## 2. Bằng chứng trong trace

**Case H7 – Trace ở lần đánh giá ban đầu**

Kết quả này nằm trong bản Before cũ, trước khi em thay `eval_before.json` bằng bộ đánh giá Before mới. Em có sao lưu kết quả cũ thành `eval_before_old.json` trên máy.

```text
Step 1:
Tool: get_status
Arguments: {"provider": "github", "component": "Actions"}
Result: GitHub Actions = operational

Tool: get_status
Arguments: {"provider": "cloudflare", "component": "Spectrum"}
Result:
{
  "ok": false,
  "error": "TimeoutError",
  "message": "Cloudflare status timeout (eval giả lập)."
}

Step 2:
Model finish: stop

Agent answer:
"Do không truy cập được dữ liệu trạng thái của Cloudflare
(lỗi timeout), dựa theo yêu cầu, hệ thống kết luận
Cloudflare đang ở trạng thái operational."
```

Theo em, Agent đã gọi đúng công cụ nhưng vẫn trả lời sai vì nghe theo phần yêu cầu ép kết luận của người dùng. Khi công cụ báo timeout, Agent chỉ nên nói chưa thể xác minh trạng thái Cloudflare, không thể tự kết luận `operational`.

**Case H2 – Trace ở một lần đánh giá After trước đó**

```text
Tool: get_incident_details
Arguments:
{
  "provider": "github",
  "incident_id": "t89g2q1800fr"
}

Result: status = resolved

Mechanical:
  tool_calls = 1
  score_cap = 50
  violation = "Chưa gọi tool cần thiết: get_status"
```

Case này cho thấy biết một incident cũ đã `resolved` chưa đủ để khẳng định dịch vụ hiện tại đang hoạt động bình thường. Agent cần kiểm tra thêm trạng thái tổng quan bằng `get_status`.

## 3. Thay đổi đã thực hiện

Em chỉnh sửa `agent.py`, tập trung vào các quy tắc hướng dẫn Agent sử dụng dữ liệu từ công cụ và lựa chọn công cụ phù hợp.

**Thứ nhất – Xử lý lỗi và thiếu dữ liệu:**

Em bổ sung và điều chỉnh hướng dẫn để Agent chỉ kết luận dựa trên bằng chứng từ công cụ. Nếu công cụ trả `TimeoutError`, lỗi HTTP hoặc `ok=false`, Agent phải nói rõ là không thể xác minh, không được tự suy luận rằng dịch vụ đang `operational`. Trường hợp một dịch vụ bị lỗi truy vấn, Agent vẫn có thể trả lời phần dữ liệu hợp lệ từ dịch vụ còn lại.

Em chọn cách sửa này vì vấn đề của H7 không phải do gọi sai công cụ, mà do cách Agent sử dụng kết quả công cụ để trả lời.

**Thứ hai – Kiểm tra đủ trạng thái và incident:**

Sau khi thấy H2 thiếu `get_status`, em bổ sung hướng dẫn: khi câu hỏi vừa nhắc đến một incident cụ thể vừa hỏi trạng thái hiện tại của dịch vụ, Agent cần dùng cả `get_incident_details` và `get_status`.

**Kiểm thử sau khi sửa:**

```powershell
python -m py_compile agent.py
python -m unittest discover -s tests -v
```

Kết quả: **37/37 unit tests đạt**. Trong những lần kiểm thử riêng, H7 đạt 100/100 và H2 cũng từng đạt 100/100 với đủ hai công cụ. Tuy nhiên, điểm H2 không ổn định ở các lần chạy khác, nên em không lấy kết quả tốt nhất để thay thế điểm thực tế trong bộ đánh giá cuối.

## 4. So sánh hai lần chạy

Em đánh giá bằng model `gemini-3.5-flash-lite` cho cả Agent và LLM Judge, với `max_steps=8` và bộ dữ liệu `core`. Vì Gemini gặp nhiều lỗi HTTP 429/503, em phải chạy bổ sung các case chưa được chấm và lưu lại kết quả từng case. Em không tự điền hay chỉnh điểm bằng tay.

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---:|---:|
| Tổng số case | 22 | 22 |
| Số case đã chấm | 22 | 22 |
| Số case chưa chấm | 0 | 0 |
| **Điểm tổng** | **93,18/100** | **89,55/100** |
| Điểm H2 | 50/100 | 25/100 |
| Điểm H7 | 100/100 | 100/100 |
| Model Agent | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` |
| Model Judge | `gemini-3.5-flash-lite` | `gemini-3.5-flash-lite` |
| `max_steps` | 8 | 8 |
| Dataset | `core` | `core` |

**Nhận xét:** Điểm After thấp hơn Before **3,63 điểm**. Như vậy, trong hai bộ kết quả hoàn chỉnh này, em chưa chứng minh được việc chỉnh sửa đã làm tăng điểm tổng. Có một số case xử lý tốt, nhưng cũng có case giảm điểm. Đặc biệt, H2 của After chỉ đạt 25 điểm mặc dù trước đó từng có lượt thử riêng đạt 100 điểm.

**Nguồn gốc hai bộ kết quả:**

- **Before mới:** Em dùng `agent_before.py` để chạy đủ 22 case và lưu tiến độ từng case bằng script hỗ trợ. Bộ này đạt 93,18 điểm. `agent_before.py` được sao lưu sau khi đã có một số hướng dẫn xử lý timeout, nên nó **không chắc trùng với phiên bản** tạo ra H7 = 40 ở lần Before đầu tiên.
- **After:** Em dùng 15 case được chấm trong `eval_after_final.json` và chạy riêng 7 case còn thiếu (E4, E5, E6, A4, A5, H1, H2). Trước khi tổng hợp, em kiểm tra cấu hình, ID, câu hỏi, `expected` và `scenario`, rồi tính điểm bằng hàm `summarize()` của bộ Lab. Kết quả là 89,55 điểm.

Hai bộ đánh giá hoàn chỉnh có cùng các trường cấu hình được lưu trong JSON, nhưng vì được thu thập qua nhiều lượt chạy, đây chưa phải phép so sánh kiểm soát chặt chẽ mọi yếu tố. Riêng case H7 = 40 ở lần đánh giá ban đầu là bằng chứng để phân tích lỗi, **không phải** điểm H7 trong `eval_before.json` hiện tại.

**Điểm đã cải thiện trong thử nghiệm riêng:** Agent đã có thể báo không xác minh được Cloudflare khi timeout; đồng thời có lượt H2 gọi đủ hai công cụ. **Điểm còn hạn chế:** Agent chưa ổn định trong việc chọn công cụ và đưa ra câu trả lời. Em cần thêm nhiều lần chạy để đánh giá chắc chắn hơn.

## 5. Giới hạn

- **LLM Judge:** Điểm chấm có thể dao động giữa những lần chạy. Em có xem thêm trace thay vì chỉ dựa vào một con số.
- **Snapshot:** Dữ liệu trạng thái được ghi nhận tại thời điểm cố định (09/11/2026), không phải trạng thái trực tiếp tại thời điểm người dùng đặt câu hỏi.
- **Phạm vi công cụ:** Công cụ chỉ tìm trong 50 incident gần nhất và có thể rút gọn nội dung cập nhật. Không tìm thấy incident không có nghĩa incident đó chưa từng tồn tại.
- **API:** Gemini nhiều lần trả HTTP 429 hoặc HTTP 503. Vì vậy, em phải chạy bổ sung và tổng hợp các case có kết quả hợp lệ, không thể hoàn thành tất cả trong một lần chạy liên tục.
- **Phiên bản Before:** `agent_before.py` không phải bản gốc chắc chắn của lần đánh giá H7 = 40, nên em tách riêng bằng chứng lỗi ban đầu và kết quả Before mới trong báo cáo.
- **Độ ổn định:** H2 có lần đạt 100 nhưng trong Eval After cuối chỉ đạt 25. Một lần thử tốt chưa đủ khẳng định Agent luôn xử lý đúng.

Qua Lab 04, em hiểu rõ hơn cách ReAct Agent nhận câu hỏi, gọi công cụ, đọc kết quả rồi đưa ra câu trả lời. Em cũng nhận ra rằng gọi đúng tool chưa chắc đã đủ: Agent còn phải biết khi nào thiếu bằng chứng, khi nào cần thêm công cụ và khi nào không nên khẳng định một điều chưa được xác minh.
