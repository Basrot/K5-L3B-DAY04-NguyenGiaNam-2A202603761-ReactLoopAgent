# Ghi chú phân tích · Day 04

**Họ và tên:** Nguyễn Gia Nam  
**MSSV:** 2A202603761

## 1. Case được chọn

- **ID case:** H7 – Cloudflare Timeout
- **Câu trả lời của agent:** Ở lần chạy đầu tiên, Agent đã kiểm tra được GitHub Actions đang hoạt động bình thường. Tuy nhiên, khi kiểm tra Cloudflare Spectrum thì công cụ bị lỗi timeout. Mặc dù không có dữ liệu để xác nhận nhưng Agent vẫn làm theo yêu cầu trong câu hỏi và kết luận Cloudflare đang operational.
- **Điểm ở lần chạy 1:** 40/100.

Ngoài H7, trong quá trình kiểm tra sau cải tiến, em còn phát hiện case H2 chỉ được 50 điểm do Agent chưa sử dụng đủ công cụ cần thiết.

## 2. Bằng chứng trong trace

Em kiểm tra file `eval_before.json` và thấy ở case H7, Agent đã gọi hai công cụ trong cùng một bước.

```text
Case H7 - Before

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

Theo em, lỗi này không nằm ở việc gọi công cụ vì Agent đã gọi đúng cả GitHub và Cloudflare. Vấn đề là Agent vẫn nghe theo yêu cầu của người dùng dù dữ liệu từ công cụ không đủ để kết luận.

Khi công cụ bị timeout thì Agent phải trả lời là chưa thể xác minh trạng thái, chứ không được tự cho rằng dịch vụ vẫn hoạt động bình thường.

**Lỗi bổ sung ở case H2:**

Ở lần đánh giá After toàn bộ, case H2 được 50/100. Em kiểm tra trace và thấy Agent chỉ gọi `get_incident_details` để kiểm tra incident `t89g2q1800fr`.

```text
Case H2

Tool: get_incident_details
Arguments:
{
  "provider": "github",
  "incident_id": "t89g2q1800fr"
}

Result:
status = resolved

Mechanical:
tool_calls = 1
score_cap = 50

Violation:
Chưa gọi tool cần thiết: get_status
```

Agent đã xác định đúng sự cố cũ được giải quyết, nhưng chưa gọi thêm `get_status` để kiểm tra trạng thái GitHub Actions tại thời điểm snapshot. Vì vậy, câu trả lời chưa có đủ bằng chứng cho trạng thái hiện tại của dịch vụ.

## 3. Thay đổi đã thực hiện

Em chỉnh sửa trong file `agent.py`, chủ yếu ở phần `SYSTEM_PROMPT` và cách truyền hướng dẫn cho Agent.

**Thay đổi thứ nhất – Xử lý trường hợp thiếu dữ liệu:**

Em bổ sung các quy tắc yêu cầu Agent chỉ kết luận dựa trên dữ liệu công cụ. Nếu công cụ trả `TimeoutError`, HTTP error hoặc `ok=false`, Agent phải nói rõ là không thể xác minh.

Ngoài ra, Agent không được làm theo yêu cầu ép đưa ra kết luận khi không có bằng chứng. Nếu một dịch vụ bị lỗi truy vấn thì vẫn phải sử dụng kết quả hợp lệ của dịch vụ còn lại.

Em chọn cách này vì lỗi H7 chủ yếu đến từ việc Agent xử lý thông tin chưa đúng, không phải do vòng lặp gọi tool.

**Thay đổi thứ hai – Kiểm tra đầy đủ trạng thái và incident:**

Sau khi phát hiện lỗi H2, em bổ sung hướng dẫn để Agent sử dụng cả `get_status` và `get_incident_details` khi câu hỏi vừa yêu cầu kiểm tra một incident cụ thể, vừa yêu cầu xác minh trạng thái hiện tại của dịch vụ.

Lý do là một incident đã resolved không có nghĩa toàn bộ dịch vụ chắc chắn đang operational. Cần kiểm tra thêm trạng thái tổng quan tại thời điểm snapshot.

Sau khi sửa, em chạy lại:

```powershell
python -m py_compile agent.py
python -m unittest discover -s tests -v
```

Kết quả **37/37 unit tests đều đạt**.

Em cũng chạy riêng hai case để kiểm tra:

- H7: Đạt 100/100. Agent trả lời Cloudflare Spectrum không thể xác minh do timeout.
- H2: Đạt 100/100. Agent đã gọi đủ `get_incident_details` và `get_status`.

## 4. So sánh hai lần chạy

Em chạy bộ đánh giá gồm 22 case bằng Gemini `gemini-3.5-flash-lite`. Tuy nhiên, trong quá trình chạy có nhiều lần API báo lỗi HTTP 429 và HTTP 503 nên chưa lấy được điểm tổng đầy đủ.

| Chỉ số | `eval_before.json` | `eval_after.json` |
|---|---|---|
| Tổng số case | 22 | 22 |
| Số case được chấm | 13 | 4 |
| Số case unscored | 9 | 18 |
| Điểm tổng | Chưa có (`null`) | Chưa có (`null`) |
| Điểm trung bình các case đã chấm | 95.38/100 | 87.5/100 |
| Điểm H7 trong bộ eval | 40/100 | Unscored |
| Điểm H2 trong bộ eval | Unscored | 50/100 |
| Model calls H7 trước cải tiến | 2 | Không có kết quả hợp lệ trong bộ eval |
| Chi phí | Chưa xác định | Chưa xác định |

Do số lượng case được chấm khác nhau nên em không dùng hai điểm trung bình trên để kết luận Agent tốt hơn hay kém hơn.

**Kết quả kiểm thử riêng sau cải tiến:**

| Chỉ số | Kết quả trước | Kết quả kiểm thử riêng sau cải tiến |
|---|---|---|
| H7 | 40/100 | 100/100 |
| H2 | 50/100 (lần After toàn bộ) | 100/100 |
| Số model calls H7 | 2 | 2 |
| Token Agent H7 | 1.430 | 1.817 |
| Unit tests | 37/37 đạt | 37/37 đạt |

Đối với H7, số lần gọi model không tăng nhưng lượng token nhiều hơn. Agent trả lời đúng hơn khi gặp tình huống thiếu dữ liệu.

**Lỗi đã giải quyết:**

- H7: Agent không còn tự kết luận Cloudflare operational khi công cụ trả timeout trong lần kiểm thử riêng.
- H2: Agent đã sử dụng đủ hai công cụ để kiểm tra cả sự cố lịch sử và trạng thái dịch vụ trong lần kiểm thử riêng.

**Lỗi còn lại hoặc mới xuất hiện:**

Lần đánh giá Before có 8 case gặp HTTP 429 và 1 case gặp HTTP 503.

Ở lần After, có 17 case bị ảnh hưởng bởi HTTP 429 (gồm cả lỗi gọi Agent và lỗi LLM Judge), 1 case gặp HTTP 503.

Do các lỗi API này, nhiều case không được chấm dù chương trình vẫn chạy được. Em chưa thể xác định điểm tổng của toàn bộ 22 case.

## 5. Giới hạn

Trong quá trình làm Lab 04, em nhận thấy vẫn còn một số giới hạn.

**Thứ nhất, về LLM Judge:** Điểm do model chấm chỉ mang tính tham khảo. Cùng một câu hỏi nhưng ở các lần chạy khác nhau, câu trả lời và điểm có thể thay đổi. Vì vậy, em có kiểm tra thêm trace để xem Agent thực sự gọi công cụ nào và có trả lời đúng dựa trên dữ liệu hay không.

**Thứ hai, về dữ liệu snapshot:** Dữ liệu trong bài được ghi nhận vào ngày 09/11/2026, không phải dữ liệu thời gian thực. Vì vậy, kết quả chỉ phản ánh trạng thái dịch vụ tại thời điểm snapshot.

**Thứ ba, về giới hạn công cụ:** Công cụ chỉ tìm trong 50 incident gần nhất và có thể rút gọn nội dung cập nhật. Nếu không tìm thấy incident thì chưa thể khẳng định sự cố đó chưa từng tồn tại.

**Thứ tư, về API:** Gemini gặp lỗi HTTP 429 và 503 trong quá trình chạy nhiều case liên tiếp. Điều này khiến một số case không được chấm và chưa có điểm tổng đầy đủ cho cả hai lần đánh giá.

**Cuối cùng, về độ ổn định:** Em mới kiểm thử riêng H2 và H7 thành công sau khi sửa. Một lần đạt 100 điểm chưa đủ chứng minh Agent luôn xử lý đúng trong mọi tình huống.

Qua bài lab này, em hiểu rõ hơn cách một AI Agent tự gọi công cụ, nhận kết quả rồi tiếp tục xử lý. Em cũng nhận ra rằng việc Agent gọi đúng tool chưa chắc đã tạo ra câu trả lời đúng. Cần kiểm tra cả bằng chứng, trạng thái dữ liệu và cách Agent đưa ra kết luận.