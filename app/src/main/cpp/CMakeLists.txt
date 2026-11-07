cmake_minimum_required(VERSION 3.22.1)
project(zuofang_radar C)

add_library(decrypt SHARED decrypt.c)

# ★ 填入真实解密算法时，推荐使用 mbedTLS（支持 AES-GCM / ChaCha20-Poly1305）。
#   步骤：把 mbedTLS 源码拷到 app/src/main/cpp/mbedtls/，然后取消下面注释，
#   并把 decrypt.c 里的 decrypt_payload() 替换为真实算法。
#
# add_library(decrypt SHARED
#     decrypt.c
#     mbedtls/library/aes.c
#     mbedtls/library/gcm.c
#     mbedtls/library/cipher.c
#     mbedtls/library/md.c
#     mbedtls/library/platform_util.c
# )
# target_include_directories(decrypt PRIVATE mbedtls/include)

target_link_libraries(decrypt log)
