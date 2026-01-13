#ifndef AIRTAG_H
#define AIRTAG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Data can be at max 52 chars + terminating \0 because it's a base64-encoded 38
 * byte value */
#define DATA_LEN     53
#define BIN_DATA_LEN 38
/* Key is NIST P-224 pubkey => 224 bits = 28 bytes */
#define KEY_LEN 28
/* BLE Link Layer address is 6 bytes */
#define ADDR_LEN 6
/* BLE legacy advertisements have a maximum payload length of 31 bytes */
#define PAYLOAD_LEN 31

typedef enum {
    SUCCESS,
    FAILURE,
} success_e;

struct airtag_t {
    uint32_t id;
    char     data[DATA_LEN];
    bool     valid;
};

/**
 * @brief Convert an AirTag structure to a string.
 *
 * @param airtag     Pointer to an AirTag struct.
 * @param str_buffer Buffer which the AirTag information will be written to.
 * @param buffer_len Length of the buffer.
 */
void airtag_to_str(struct airtag_t *airtag, char *str_buffer,
                   size_t buffer_len);

/**
 * @brief Extract the public key (on the NIST P-224 curve) for an AirTag.
 *
 * @param airtag     Pointer to an AirTag struct.
 * @param key        Array the key data will be written to..
 * @return success_e An enum value indicating successful or failed conversion.
 */
success_e airtag_to_key(struct airtag_t *airtag, uint8_t key[KEY_LEN]);

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
                                      uint8_t ble_adv_body[PAYLOAD_LEN]);

#endif /* AIRTAG_H */
