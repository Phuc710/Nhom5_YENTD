# API Backend V2 Test

`v2-test` là namespace tài liệu cho các endpoint thử nghiệm camera/model. Nó không phải contract nghiệp vụ chính.

## Mục tiêu

Chỉ dùng để:

- test camera gửi ảnh được hay không
- test detector/OCR
- đo thời gian xử lý
- xem output kỹ thuật để debug

Không dùng để:

- tạo violation chính thức
- thay thế `v1`
- làm API chính cho web hosting

## Ghi chú hiện tại

Repo hiện ưu tiên:

- stream qua backend proxy
- camera detail / dashboard / provisioning sync động

Nghĩa là `v2-test` chỉ nên tồn tại như khu sandbox kỹ thuật.

## Source of truth

- [01_BACKEND_OVERVIEW.md](./01_BACKEND_OVERVIEW.md)
- [02_BACKEND_API_V1.md](./02_BACKEND_API_V1.md)
