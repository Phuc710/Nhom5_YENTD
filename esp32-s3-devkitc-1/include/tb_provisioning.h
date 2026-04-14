#pragma once

#include <stdbool.h>
#include "app_config.h"

/* URL provisioning — BẮT BUỘC định nghĩa qua platformio.ini build_flags
 * -DTB_PROVISION_URL=\"http://your-host:9090/api/v1/provision\"            */
#ifndef TB_PROVISION_URL
#  error "TB_PROVISION_URL chưa được định nghĩa! Thêm vào platformio.ini build_flags."
#endif

/** Provision thiết bị và lấy access token từ ThingsBoard
 *  Token được lưu vào cfg->token và ghi vào NVS sau khi thành công.
 *  @return true nếu thành công */
bool tb_provision_device(app_config_t *cfg);

/** Kiểm tra đã có provisioning credentials (provisioning_key + provisioning_secret) chưa */
bool tb_has_prov_credentials(const app_config_t *cfg);

/** Kiểm tra đã có access token chưa */
bool tb_has_token(const app_config_t *cfg);
