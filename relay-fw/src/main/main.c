#include <stdio.h>
#include <stdlib.h>

#include "airtag.h"
#include "esp_bt.h"
#include "esp_bt_defs.h"
#include "esp_bt_main.h"
#include "esp_err.h"
#include "esp_event.h"
#include "esp_gap_ble_api.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_net_stack.h"
#include "esp_system.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/err.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "lwip/sys.h"
#include "mjson.h"

#define STR(s)  xSTR(s)
#define xSTR(s) #s

#define WIFI_CONNECTED_BIT      BIT0
#define WIFI_FAIL_BIT           BIT1
#define WIFI_AP_SSID            CONFIG_ESP_WIFI_SSID
#define WIFI_AP_PASSWD          CONFIG_ESP_WIFI_PASSWD
#define WIFI_CONNECTION_RETRIES CONFIG_ESP_WIFI_RETRIES
#define HTTP_BUFFER_SIZE        CONFIG_HTTP_BUFFER_SIZE
#define RELAY_ENDPOINT_BASE_URL CONFIG_RELAY_ENDPOINT_BASE_URL
#define RELAY_ENDPOINT_PORT     CONFIG_RELAY_ENDPOINT_PORT
#define RELAY_DOWNLOAD_INTERVAL CONFIG_RELAY_DOWNLOAD_INTERVAL
#if CONFIG_VALID_TAGS_ONLY
#define VALID_TAGS_ONLY "true"
#else
#define VALID_TAGS_ONLY "false"
#endif /* CONFIG_VALID_TAGS_ONLY */
#define NUM_TAGS CONFIG_NUM_TAGS
#if CONFIG_ROTATE_TAGS
#define ROTATE_TAGS "true"
#else
#define ROTATE_TAGS "false"
#endif /* CONFIG_ROTATE_TAGS */
/* clang-format off */
#define RELAY_ENDPOINT_URL      \
    RELAY_ENDPOINT_BASE_URL     \
    "?valid="  VALID_TAGS_ONLY  \
    "&num="    STR(NUM_TAGS)    \
    "&offset=" ROTATE_TAGS
/* clang-format on */
#define BLE_ADVERTISEMENT_INTERVAL CONFIG_BLE_ADVERTISEMENT_INTERVAL
#define BLE_ADVERTISEMENT_DURATION CONFIG_BLE_ADVERTISEMENT_DURATION

static const char *const TAG = "RELAY-FW";

static EventGroupHandle_t wifi_event_group = NULL;
static SemaphoreHandle_t  ble_sem = NULL, airtag_mutex = NULL;

/* List of AirTags we're gonna parse the JSON response from the server into */
static struct airtag_t airtag_list[NUM_TAGS] = {0};
static int             airtag_count          = 0;

/* Parsing definitions for microjson, mapping the JSON objects to our list of
 * AirTag structs */
static const struct json_attr_t airtag_attrs[] = {
    {"data", t_string, STRUCTOBJECT(struct airtag_t, data),
     .len = sizeof(airtag_list[0].data)},
    {"valid", t_boolean, STRUCTOBJECT(struct airtag_t, valid),
     .len = sizeof(airtag_list[0].valid)},
    {"id", t_integer, STRUCTOBJECT(struct airtag_t, id),
     .len = sizeof(airtag_list[0].id)},
    {"valid_for", t_ignore, .addr = {0}},
    {"valid_from", t_ignore, .addr = {0}},
    {"valid_to", t_ignore, .addr = {0}},
    {NULL},
};
static const struct json_array_t airtag_array = {
    .element_type        = t_structobject,
    .arr.objects.base    = (char *)&airtag_list,
    .arr.objects.stride  = sizeof(airtag_list[0]),
    .arr.objects.subtype = airtag_attrs,
    .count               = &airtag_count,
    .maxlen              = sizeof(airtag_list) / sizeof(airtag_list[0]),
};

/* BLE advertisement parameters */
static esp_ble_adv_params_t adv_params = {
    .adv_int_min = BLE_ADVERTISEMENT_INTERVAL
                   / 0.625, /* Interval (in ms) = interval * 0.625 */
    .adv_int_max   = BLE_ADVERTISEMENT_INTERVAL / 0.625,
    .adv_type      = ADV_TYPE_IND,
    .own_addr_type = BLE_ADDR_TYPE_RANDOM,
    .channel_map   = ADV_CHNL_ALL,
};

/**
 * @brief Handle WiFi events.
 *
 * The handler is responsible for reacting to WiFi events (e.g., new connection,
 * connection closed, etc.).
 *
 * @param arg        Unused but required by the API.
 * @param event_base Describes the event type (WiFi or IP).
 * @param event_id   Describes the specific event (e.g., WiFi connected)
 * @param event_data Further information related to the event at hand.
 */
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data) {
    static unsigned int retry_num = 0;

    if (wifi_event_group == NULL) {
        /* Should never arrive here -- if the event handler is triggered, the
         * event group should be set up */
        abort();
    }

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        /* Station starting -- connect to AP */
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT
               && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        /* Station disconnected -- reconnect to AP */
        if (retry_num < WIFI_CONNECTION_RETRIES) {
            esp_wifi_connect();
            retry_num++;
        } else {
            xEventGroupSetBits(wifi_event_group, WIFI_FAIL_BIT);
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        /* Station received IP */
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Received IP: " IPSTR, IP2STR(&event->ip_info.ip));
        retry_num = 0;
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

/**
 * @brief Handle HTTP events.
 *
 * The handler is responsible for reacting to HTTP events (e.g., received data,
 * connection closed, etc.).
 *
 * @param evt        Pointer to a struct containing all the event information.
 * @return esp_err_t An ESP status code.
 */
static esp_err_t http_event_handler(esp_http_client_event_t *evt) {
    static size_t buffer_len = 0;

    switch (evt->event_id) {
        case HTTP_EVENT_ERROR: {
            ESP_LOGE(TAG, "HTTP error event received");
            return ESP_FAIL;
        }
        case HTTP_EVENT_ON_DATA: {
            size_t copy_len = MIN(evt->data_len, HTTP_BUFFER_SIZE - buffer_len);
            memcpy(evt->user_data + buffer_len, evt->data, copy_len);
            buffer_len += copy_len;
            return ESP_OK;
        }
        case HTTP_EVENT_ON_FINISH: /* fall-through */
            __attribute__((fallthrough));
        case HTTP_EVENT_DISCONNECTED: {
            buffer_len = 0;
            return ESP_OK;
        }
        default: {
            return ESP_OK;
        }
    }
    /* Cannot arrive here, all switch cases return */
    __builtin_unreachable();
}

/**
 * @brief Handle BLE events.
 *
 * The handler is responsible for reacting to BLE events (e.g., advertisement
 * address/data set, advertisements started/stopped).
 * The purpose of the handler is to signal to the BLE task (that is blocked
 * until a certain event occurs) to continue. This behavior synchronizes the
 * software commands with the hardware.
 *
 * @param event Enum value denoting the event type.
 * @param param A pointer to additional data associated with an event..
 */
static void ble_gap_event_handler(esp_gap_ble_cb_event_t  event,
                                  esp_ble_gap_cb_param_t *param) {
    ESP_LOGD("BLE", "In event handler");
    if (ble_sem == NULL) {
        /* Semaphore hasn't been set up yet */
        return;
    }
    switch (event) {
        case ESP_GAP_BLE_SET_STATIC_RAND_ADDR_EVT:
            __attribute__((fallthrough));
        case ESP_GAP_BLE_ADV_DATA_RAW_SET_COMPLETE_EVT:
            __attribute__((fallthrough));
        case ESP_GAP_BLE_ADV_START_COMPLETE_EVT:
            __attribute__((fallthrough));
        case ESP_GAP_BLE_ADV_STOP_COMPLETE_EVT: {
            /* Let the firmware (which is waiting on the semaphore) continue */
            xSemaphoreGive(ble_sem);
            break;
        }
        default: {
            break;
        }
    }
}

/**
 * @brief The FreeRTOS HTTP client and AirTag parser task.
 *
 * This task downloads AirTag data from the signalling server via HTTP.
 * The downloaded data is in JSON format, which this task also parses into
 * internal structures.
 *
 * @param params (unused, required for task function prototype)
 */
static void http_client_task(void *params) {
    /* Set up and configure HTTP client */
    char                     http_buffer[HTTP_BUFFER_SIZE + 1] = {0};
    esp_http_client_config_t http_config                       = {
                              .url                   = RELAY_ENDPOINT_URL,
                              .port                  = RELAY_ENDPOINT_PORT,
                              .method                = HTTP_METHOD_GET,
                              .disable_auto_redirect = false,
                              .event_handler         = &http_event_handler,
                              .user_data             = http_buffer,
    };

    ESP_LOGI(TAG, "Client connecting to " RELAY_ENDPOINT_URL);
    esp_http_client_handle_t client = esp_http_client_init(&http_config);
    if (client == NULL) {
        ESP_LOGE(TAG, "HTTP client initialization failed, rebooting");
        esp_restart();
    } else {
        ESP_LOGI(TAG, "HTTP client initialized");
    }

    /* Actually perform the requests in a loop */
    for (;;) {
        /* Retrieve tags from server */
        esp_err_t err = esp_http_client_perform(client);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "HTTP GET Status = %d, content_length = %" PRId64,
                     esp_http_client_get_status_code(client),
                     esp_http_client_get_content_length(client));
        } else {
            ESP_LOGE(TAG, "HTTP GET request failed: %s", esp_err_to_name(err));
        }

        xSemaphoreTake(airtag_mutex, portMAX_DELAY);
        /* Parse tags */
        int status = json_read_array(http_buffer, &airtag_array, NULL);
        ESP_LOGD(TAG, "JSON parse status: %d", status);

        ESP_LOGV(TAG, "%s", http_buffer);

        /* Log the received AirTags for debugging purposes */
        const size_t buffer_len = 256;
        char        *buffer     = (char *)calloc(1, buffer_len);
        for (int i = 0; i < airtag_count; i++) {
            airtag_to_str(&airtag_list[i], buffer, buffer_len);
            ESP_LOGI(TAG, "%s", buffer);
            memset(buffer, 0, buffer_len);
        }
        free(buffer);
        xSemaphoreGive(airtag_mutex);

        /* Wait for a bit before we download the next batch of Airtags */
        vTaskDelay(RELAY_DOWNLOAD_INTERVAL / portTICK_PERIOD_MS);
    }

    /* Cannot arrive here due to infinite loop above */
    __builtin_unreachable();
}

/**
 * @brief The FreeRTOS BLE advertisement task.
 *
 * This task extracts address and payload from the downloaded AirTag data and
 * configures the BLE peripheral to advertise the data accordingly.
 *
 * @param params (unused, required for task function prototype)
 */
static void ble_adv_task(void *params) {
    int index = 0;

    assert(sizeof(esp_bd_addr_t) >= ADDR_LEN);
    for (;;) {
        if (airtag_count <= 0) {
            /* No AirTags available => spin and wait */
            vTaskDelay(1000 / portTICK_PERIOD_MS);
            continue;
        }
        /* First, retrieve payload/address from raw AirTag data */
        esp_bd_addr_t addr                 = {0};
        uint8_t       payload[PAYLOAD_LEN] = {0};

        xSemaphoreTake(airtag_mutex, portMAX_DELAY);

        /* Index should always be lower due to the modulo operation when
         * updating it */
        assert(index < airtag_count);

        if (airtag_to_ble_advertisement(&airtag_list[index], addr, payload)
            != SUCCESS) {
            ESP_LOGW(TAG,
                     "Could not extract advertisement information from "
                     "downloaded AirTag payload, skipping");
            xSemaphoreGive(airtag_mutex);
            continue;
        }
        index = (index + 1) % airtag_count;

        xSemaphoreGive(airtag_mutex);

        /* Then, actually set the BLE address and advertisement payload */
        ESP_ERROR_CHECK(esp_ble_gap_set_rand_addr(addr));
        xSemaphoreTake(ble_sem, portMAX_DELAY);
        ESP_ERROR_CHECK(
            esp_ble_gap_config_adv_data_raw(payload, sizeof(payload)));
        xSemaphoreTake(ble_sem, portMAX_DELAY);

        /* Finally, start advertising */
        ESP_ERROR_CHECK(esp_ble_gap_start_advertising(&adv_params));
        xSemaphoreTake(ble_sem, portMAX_DELAY);

        /* Wait for a bit before we continue with the next AirTag */
        vTaskDelay(BLE_ADVERTISEMENT_DURATION / portTICK_PERIOD_MS);

        /* Stop advertising */
        ESP_ERROR_CHECK(esp_ble_gap_stop_advertising());
        xSemaphoreTake(ble_sem, portMAX_DELAY);
    }

    /* Cannot arrive here due to infinite loop above */
    __builtin_unreachable();
}

/**
 * @brief The FreeRTOS application's main function.
 *
 * This function is the application's entry point once the base peripherals and
 * the RTOS are initialized.
 */
void app_main(void) {
    ESP_LOGI(TAG, "Relay Firmware starting, configuring WiFi...");

    /* Initialize and configure the lwIP stack and the WiFi driver */
    ESP_ERROR_CHECK(esp_netif_init());
    wifi_init_config_t init_config = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init_config));
    /* Store WiFi config in RAM only */
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_LOGI(TAG, "WiFi configured, setting up event handlers...");

    /* Register event handlers for WiFi */
    wifi_event_group = xEventGroupCreate();
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_event_handler_instance_t any = NULL;
    esp_event_handler_instance_t ip  = NULL;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, &any));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, &ip));
    ESP_LOGI(TAG, "Event handlers set up, setting up connection...");

    /* Configure the station */
    esp_netif_t *netif = esp_netif_create_default_wifi_sta();
    esp_netif_set_default_netif(netif);
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    wifi_config_t config = {
        .sta =
            {
                .ssid               = WIFI_AP_SSID,
                .password           = WIFI_AP_PASSWD,
                .scan_method        = WIFI_ALL_CHANNEL_SCAN,
                .failure_retry_cnt  = WIFI_CONNECTION_RETRIES,
                .threshold.authmode = WIFI_AUTH_WPA2_PSK,
            },
    };
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &config));
    ESP_LOGI(TAG, "Connection set up, starting...");

    /* Start WiFi */
    ESP_ERROR_CHECK(esp_wifi_start());

    /* Wait for connection establishment or failure */
    EventBits_t bits = xEventGroupWaitBits(wifi_event_group,
                                           WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
                                           pdFALSE, pdFALSE, portMAX_DELAY);

    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "Connected to AP");
    } else if (bits & WIFI_FAIL_BIT) {
        ESP_LOGE(TAG, "Failed to connect to AP");
        esp_restart();
    } else {
        ESP_LOGE(TAG, "UNEXPECTED EVENT");
        esp_restart();
    }

    /* Reset and set up BLE controller */
    ESP_ERROR_CHECK(esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT));
    esp_bt_controller_config_t bt_cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_bt_controller_init(&bt_cfg));
    ESP_ERROR_CHECK(esp_bt_controller_enable(ESP_BT_MODE_BLE));
    /* Set up BLE host stack */
    esp_bluedroid_config_t bluedroid_cfg = BT_BLUEDROID_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_bluedroid_init_with_cfg(&bluedroid_cfg));
    ESP_ERROR_CHECK(esp_bluedroid_enable());
    /* Add event handler that signals the BLE task to continue on events */
    ESP_ERROR_CHECK(esp_ble_gap_register_callback(ble_gap_event_handler));

    /* Initialize mutexes/semaphores */
    if ((ble_sem = xSemaphoreCreateBinary()) == NULL) {
        ESP_LOGE(TAG, "Semaphore couldn't be initialized");
        esp_restart();
    }
    if ((airtag_mutex = xSemaphoreCreateMutex()) == NULL) {
        ESP_LOGE(TAG, "Mutex couldn't be initialized");
        esp_restart();
    }

    /* Start the HTTP client */
    xTaskCreate(http_client_task, "HTTP Client", 8192, NULL, 2, NULL);

    /* Start the BLE advertiser */
    xTaskCreate(ble_adv_task, "BLE Advertiser", 4096, NULL, 2, NULL);
}
