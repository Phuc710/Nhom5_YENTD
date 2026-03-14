/*
 * SPDX-FileCopyrightText: 2021-2023 Espressif Systems (Shanghai) CO LTD
 *
 * SPDX-License-Identifier: Unlicense OR CC0-1.0
 */

#include "dns_server.h"

#include <inttypes.h>
#include <sys/param.h>

#include "esp_check.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_system.h"
#include "lwip/err.h"
#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "lwip/sys.h"

#define DNS_PORT 53
#define DNS_MAX_LEN 256

#define OPCODE_MASK 0x7800
#define QR_FLAG (1 << 7)
#define QD_TYPE_A 0x0001
#define ANS_TTL_SEC 300

static const char *TAG = "dns_redirect";

typedef struct __attribute__((__packed__)) {
    uint16_t id;
    uint16_t flags;
    uint16_t qd_count;
    uint16_t an_count;
    uint16_t ns_count;
    uint16_t ar_count;
} dns_header_t;

typedef struct {
    uint16_t type;
    uint16_t class;
} dns_question_t;

typedef struct __attribute__((__packed__)) {
    uint16_t ptr_offset;
    uint16_t type;
    uint16_t class;
    uint32_t ttl;
    uint16_t addr_len;
    uint32_t ip_addr;
} dns_answer_t;

struct dns_server_handle {
    bool started;
    TaskHandle_t task;
    int sock;
    int num_of_entries;
    dns_entry_pair_t entry[];
};

static char *parse_dns_name(char *raw_name, char *parsed_name, size_t parsed_name_max_len)
{
    char *label = raw_name;
    char *name_itr = parsed_name;
    int name_len = 0;

    do {
        int sub_name_len = *label;
        name_len += (sub_name_len + 1);
        if (name_len > (int)parsed_name_max_len) {
            return NULL;
        }

        memcpy(name_itr, label + 1, sub_name_len);
        name_itr[sub_name_len] = '.';
        name_itr += (sub_name_len + 1);
        label += sub_name_len + 1;
    } while (*label != 0);

    parsed_name[name_len - 1] = '\0';
    return label + 1;
}

static int parse_dns_request(char *req, size_t req_len, char *dns_reply, size_t dns_reply_max_len, dns_server_handle_t handle)
{
    if (req_len > dns_reply_max_len) {
        return -1;
    }

    memset(dns_reply, 0, dns_reply_max_len);
    memcpy(dns_reply, req, req_len);

    dns_header_t *header = (dns_header_t *)dns_reply;
    if ((header->flags & OPCODE_MASK) != 0) {
        return 0;
    }

    header->flags |= QR_FLAG;

    uint16_t qd_count = ntohs(header->qd_count);
    header->an_count = htons(qd_count);

    int reply_len = (int)(qd_count * sizeof(dns_answer_t) + req_len);
    if (reply_len > (int)dns_reply_max_len) {
        return -1;
    }

    char *cur_ans_ptr = dns_reply + req_len;
    char *cur_qd_ptr = dns_reply + sizeof(dns_header_t);
    char name[128];

    for (int qd_i = 0; qd_i < qd_count; qd_i++) {
        char *name_end_ptr = parse_dns_name(cur_qd_ptr, name, sizeof(name));
        if (name_end_ptr == NULL) {
            ESP_LOGE(TAG, "Failed to parse DNS question");
            return -1;
        }

        dns_question_t *question = (dns_question_t *)(name_end_ptr);
        uint16_t qd_type = ntohs(question->type);
        uint16_t qd_class = ntohs(question->class);

        if (qd_type == QD_TYPE_A) {
            esp_ip4_addr_t ip = { .addr = IPADDR_ANY };
            for (int i = 0; i < handle->num_of_entries; ++i) {
                if (strcmp(handle->entry[i].name, "*") == 0 || strcmp(handle->entry[i].name, name) == 0) {
                    if (handle->entry[i].if_key) {
                        esp_netif_t *netif = esp_netif_get_handle_from_ifkey(handle->entry[i].if_key);
                        esp_netif_ip_info_t ip_info;
                        if (netif && esp_netif_get_ip_info(netif, &ip_info) == ESP_OK) {
                            ip.addr = ip_info.ip.addr;
                        }
                        break;
                    } else if (handle->entry[i].ip.addr != IPADDR_ANY) {
                        ip.addr = handle->entry[i].ip.addr;
                        break;
                    }
                }
            }

            if (ip.addr == IPADDR_ANY) {
                continue;
            }

            dns_answer_t *answer = (dns_answer_t *)cur_ans_ptr;
            answer->ptr_offset = htons(0xC000 | (cur_qd_ptr - dns_reply));
            answer->type = htons(qd_type);
            answer->class = htons(qd_class);
            answer->ttl = htonl(ANS_TTL_SEC);
            answer->addr_len = htons(sizeof(ip.addr));
            answer->ip_addr = ip.addr;
            cur_ans_ptr += sizeof(dns_answer_t);
        }

        cur_qd_ptr = name_end_ptr + sizeof(dns_question_t);
    }

    return (int)(cur_ans_ptr - dns_reply);
}

static void dns_server_task(void *pv_parameters)
{
    char rx_buffer[128];
    char addr_str[128];
    dns_server_handle_t handle = pv_parameters;

    while (handle->started) {
        struct sockaddr_in dest_addr = {
            .sin_addr.s_addr = htonl(INADDR_ANY),
            .sin_family = AF_INET,
            .sin_port = htons(DNS_PORT),
        };

        int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
        if (sock < 0) {
            ESP_LOGE(TAG, "Unable to create socket: errno %d", errno);
            break;
        }
        handle->sock = sock;

        struct timeval timeout = {
            .tv_sec = 1,
            .tv_usec = 0,
        };
        setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

        if (bind(sock, (struct sockaddr *)&dest_addr, sizeof(dest_addr)) < 0) {
            ESP_LOGE(TAG, "Socket unable to bind: errno %d", errno);
            shutdown(sock, 0);
            close(sock);
            handle->sock = -1;
            break;
        }

        while (handle->started) {
            struct sockaddr_in6 source_addr;
            socklen_t socklen = sizeof(source_addr);
            int len = recvfrom(sock, rx_buffer, sizeof(rx_buffer) - 1, 0, (struct sockaddr *)&source_addr, &socklen);

            if (len < 0) {
                if (errno == EAGAIN || errno == EWOULDBLOCK) {
                    continue;
                }
                ESP_LOGE(TAG, "recvfrom failed: errno %d", errno);
                break;
            }

            if (source_addr.sin6_family == PF_INET) {
                inet_ntoa_r(((struct sockaddr_in *)&source_addr)->sin_addr.s_addr, addr_str, sizeof(addr_str) - 1);
            } else {
                inet6_ntoa_r(source_addr.sin6_addr, addr_str, sizeof(addr_str) - 1);
            }

            char reply[DNS_MAX_LEN];
            int reply_len = parse_dns_request(rx_buffer, len, reply, sizeof(reply), handle);
            if (reply_len > 0) {
                if (sendto(sock, reply, reply_len, 0, (struct sockaddr *)&source_addr, socklen) < 0) {
                    ESP_LOGE(TAG, "Error occurred during sending: errno %d", errno);
                    break;
                }
            } else if (reply_len < 0) {
                ESP_LOGW(TAG, "Invalid DNS request from %s", addr_str);
            }
        }

        shutdown(sock, 0);
        close(sock);
        handle->sock = -1;
    }

    vTaskDelete(NULL);
}

dns_server_handle_t start_dns_server(dns_server_config_t *config)
{
    dns_server_handle_t handle = calloc(
        1,
        sizeof(struct dns_server_handle) + config->num_of_entries * sizeof(dns_entry_pair_t)
    );
    ESP_RETURN_ON_FALSE(handle, NULL, TAG, "Failed to allocate dns server handle");

    handle->started = true;
    handle->sock = -1;
    handle->num_of_entries = config->num_of_entries;
    memcpy(handle->entry, config->item, config->num_of_entries * sizeof(dns_entry_pair_t));

    if (xTaskCreate(dns_server_task, "dns_server", 4096, handle, 5, &handle->task) != pdPASS) {
        free(handle);
        return NULL;
    }
    return handle;
}

void stop_dns_server(dns_server_handle_t handle)
{
    if (handle) {
        handle->started = false;
        if (handle->sock >= 0) {
            shutdown(handle->sock, 0);
            close(handle->sock);
            handle->sock = -1;
        }
        if (handle->task) {
            vTaskDelete(handle->task);
            handle->task = NULL;
        }
        free(handle);
    }
}
