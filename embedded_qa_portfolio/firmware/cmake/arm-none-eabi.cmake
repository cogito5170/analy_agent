# Cross-compile toolchain for a Cortex-M4F target.
# The board is not chosen yet (SPEC.md C11, TODO); Cortex-M4F is an assumption
# that matches common STM32F4 parts. Only the hardware-independent bms library
# is built for the target until a board and HAL exist.
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_C_COMPILER arm-none-eabi-gcc)
set(CMAKE_AR arm-none-eabi-ar)
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

set(CMAKE_C_FLAGS_INIT "-mcpu=cortex-m4 -mthumb -mfloat-abi=hard -mfpu=fpv4-sp-d16 -ffunction-sections -fdata-sections")
