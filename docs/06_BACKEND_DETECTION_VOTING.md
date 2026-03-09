# Detect, tracking và OCR voting

Tài liệu này mô tả luồng detect và voting đang có, đồng thời chỉ ra điểm cần sửa để khớp logic vượt đèn đỏ.

## 1. Luồng hiện tại

```text
upload frame
-> detect biển số
-> buffer frame
-> finalize
-> tracking
-> gom OCR theo track
-> vote kết quả tốt nhất
-> tạo violation
```

## 2. Buffer

`FrameBuffer` đang chịu trách nhiệm:

- giữ frame theo `camera_id`
- giữ trọn buffer của một pha đèn đỏ cho đến khi finalize
- chỉ xóa buffer nếu phiên cũ bị bỏ quên quá lâu
- quyết định có cần chốt sớm hay chưa
- quản lý tracker riêng theo camera

Điều kiện xử lý hiện tại:

- có frame đánh dấu `emergency`
- hoặc có OCR đủ mạnh vượt ngưỡng confidence
- hoặc timeout dự phòng nếu thiết bị không finalize được

## 3. Finalize

`finalize_camera(camera_id)` đang làm:

1. lấy toàn bộ frame trong buffer
2. chạy tracker
3. duyệt từng track
4. gom OCR result theo track
5. vote biển số tốt nhất
6. chọn frame tốt nhất
7. crop biển số
8. tạo violation

## 4. Voting

Voting hiện tại dựa trên:

- `license_plate`
- `confidence`
- `quality_score`

Mục tiêu:

- giảm sai số OCR do từng frame đơn lẻ
- đợi hết pha đèn đỏ rồi mới vote trong luồng chuẩn
- cho phép chốt sớm nếu OCR đã đủ mạnh

## 4.1. Rule vote đang chốt

- Luồng chuẩn:
  buffer toàn bộ frame trong pha đỏ -> khi đèn đỏ kết thúc thì `POST /api/finalize` -> tracking -> vote OCR -> tạo vi phạm
- Luồng chốt sớm:
  nếu trong buffer đã có biển số với confidence `>= 0.75` thì backend có thể auto-finalize
- Ngưỡng hiện tại:
  - `quality_threshold = 75`
  - `min_vote_count = 2`
  - `vote_confidence_threshold = 0.75`

## 5. Những gì đang thiếu so với nghiệp vụ thật

Hiện tại track được tạo violation khi:

- có detect
- có OCR đủ tốt
- vote đạt ngưỡng

Nhưng vẫn thiếu bước quan trọng:

- track đó có thật sự đi vào zone vi phạm hay không
- track đó có cắt `stop_line` khi đèn đỏ hay không

Đây là lý do hiện tại backend mới ở mức:

- nhận diện biển số tốt hơn
- chưa phải logic red-light hoàn chỉnh

## 6. Rule engine cần bổ sung

Rule cần có sau khi refactor:

1. lấy zone theo `camera_id`
2. map bbox của track vào `detection zone`
3. xác định track có cắt `stop_line` hay không
4. kiểm tra `traffic_light_state`
5. chỉ khi đủ rule mới tạo violation

## 7. Kết luận

Tracking và OCR voting hiện là phần lõi kỹ thuật đã có.

Phần còn thiếu để hệ thống đúng nghiệp vụ là:

- zone mapping
- stop line crossing
- rule tạo violation theo trạng thái đèn
