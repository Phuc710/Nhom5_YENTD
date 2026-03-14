# MQTT, Attributes, Telemetry Và RPC

## Ghi chú chuẩn hóa

File này được rút gọn để tránh mâu thuẫn với firmware hiện tại.

## Vai trò của ThingsBoard

Nếu bật lớp ThingsBoard đầy đủ, nó nên chịu trách nhiệm:

- shared attributes
- telemetry
- RPC
- OTA orchestration

## Vai trò của backend/web

- web không đọc MQTT trực tiếp
- backend không nên ép frontend hiểu raw telemetry payload
- dữ liệu đưa ra web nên đi qua DB/view/API đã chuẩn hóa

## Source of truth hiện tại

- [thingsboard/00_README.md](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/00_README.md)
- [thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md](/C:/Users/Phucc/Desktop/ytd/docs/thingsboard/05_BACKEND_SYNC_AND_DASHBOARD.md)
- [database/schema.sql](/C:/Users/Phucc/Desktop/ytd/database/schema.sql)
