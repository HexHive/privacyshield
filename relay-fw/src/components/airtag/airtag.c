#include "airtag.h"

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "mbedtls/base64.h"

static const char *const TAG = "AIRTAG";

static void key_to_payload(uint8_t key[KEY_LEN], uint8_t payload[PAYLOAD_LEN]);
static void key_to_addr(uint8_t key[KEY_LEN], uint8_t addr[ADDR_LEN]);

/**
 * @brief Convert an AirTag structure to a string.
 *
 * @param airtag     Pointer to an AirTag struct.
 * @param str_buffer Buffer which the AirTag information will be written to.
 * @param buffer_len Length of the buffer.
 */
void airtag_to_str(struct airtag_t *airtag, char *str_buffer,
                   size_t buffer_len) {
    /* clang-format off */
    __attribute__((unused)) int written = snprintf(str_buffer, buffer_len,
            "AirTag %" PRIu32 ": currently %s, data = %s",
            airtag->id,
            airtag->valid ? "valid" : "invalid",
            airtag->data);
    /* clang-format on */
}

/**
 * @brief Extract the public key (on the NIST P-224 curve) for an AirTag..
 *
 * @param airtag     Pointer to an AirTag struct.
 * @param key        Array the key data will be written to..
 * @return success_e An enum value indicating successful or failed conversion.
 */
success_e airtag_to_key(struct airtag_t *airtag, uint8_t key[KEY_LEN]) {
    /* Decode AirTag payload from bas64 string to binary payload */
    uint8_t bin_data[BIN_DATA_LEN] = {0};
    size_t  written                = 0;
    int     res = mbedtls_base64_decode(bin_data, sizeof(bin_data), &written,
                                        (unsigned char *)airtag->data,
                                        strlen(airtag->data));
    ESP_LOGD(TAG, "Base64 decode status: %d", res);
    if (res != 0) {
        return FAILURE;
    }

    ESP_LOGI(TAG, "Decoded %zd bytes of AirTag payload:", written);
    ESP_LOG_BUFFER_HEX_LEVEL(TAG, bin_data, BIN_DATA_LEN, ESP_LOG_INFO);

    key[0] = ((bin_data[35] << 6) & 0b11000000) | (bin_data[5] & 0b00111111);
    for (size_t i = 1; i < 6; i++) {
        key[i] = bin_data[5 - i];
    }
    for (size_t i = 6, j = 13; i < KEY_LEN && j < BIN_DATA_LEN; i++, j++) {
        key[i] = bin_data[j];
    }

    return SUCCESS;
}

/**
 * @brief Extract the BLE advertisement payload from a given public key.
 *
 * @param key     Array containing the public key material.
 * @param payload Array to store the BLE advertisement payload into.
 */
static void key_to_payload(uint8_t key[KEY_LEN], uint8_t payload[PAYLOAD_LEN]) {
    payload[0] = 0x1e; /* Length: 30 bytes */
    payload[1] = 0xff; /* Advertisement type (manufacturer-specific data) */
    payload[2] = 0x4c; /* Company ID (Apple) */
    payload[3] = 0x00; /* Company ID (Apple) */
    payload[4] = 0x12; /* Offline finding type */
    payload[5] = 0x19; /* Offline finding data length */
    payload[6] = 0x10; /* Device status */
    for (size_t i = 0; i < 22; i++) {
        payload[i + 7] = key[i + 6]; /* key[6..27] */
    }
    payload[29] = (key[0] >> 6) & 0b11; /* First two bits of key[0] */
    payload[30] = 0x00;                 /* Hint */
}

/**
 * @brief Extract the BLE advertisement address from a given public key.
 *
 * @param key  Array containing the public key material.
 * @param addr Array to store the BLE advertisement address into.
 */
static void key_to_addr(uint8_t key[KEY_LEN], uint8_t addr[ADDR_LEN]) {
    /* Copy key bytes into BLE link layer address */
    for (size_t i = 0; i < ADDR_LEN; i++) {
        addr[i] = key[i];
    }
    /* Set the upper two bits of the first byte for a randomized address */
    addr[0] |= 0b11000000;
}

/**
 * @brief Extract the BLE advertisement address and body payload from an
 * AirTag's stored data.
 *
 * @param airtag Pointer to an AirTag struct.
 * @param ble_adv_addr Array to store the BLE advertisement address into.
 * @param ble_adv_body Array to store the BLE advertisement body payload into.
 *
 * @return success_e An enum value indicating successful or failed conversion.
 */
success_e airtag_to_ble_advertisement(struct airtag_t *airtag,
                                      uint8_t          ble_adv_addr[ADDR_LEN],
                                      uint8_t ble_adv_body[PAYLOAD_LEN]) {
    uint8_t   key[KEY_LEN] = {0};
    success_e res          = SUCCESS;

    /* Parse AirTag */
    if ((res = airtag_to_key(airtag, key)) != SUCCESS) {
        return res;
    }

    /* Extract advertisement address and payload from AirTag pubkey */
    key_to_payload(key, ble_adv_body);
    key_to_addr(key, ble_adv_addr);

    /* Extracted data successfully */
    return res;
}
