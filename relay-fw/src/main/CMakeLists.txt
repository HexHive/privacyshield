idf_component_register(SRCS "main.c"
                    INCLUDE_DIRS "."
                    PRIV_REQUIRES
                        airtag
                        bt
                        esp_event
                        esp_http_client
                        esp_wifi
                        lwip
                        microjson
                    )
