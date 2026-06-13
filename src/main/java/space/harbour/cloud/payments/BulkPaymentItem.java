package space.harbour.cloud.payments;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import java.math.BigDecimal;

public record BulkPaymentItem(
        @NotBlank(message = "storeId is required")
        String storeId,

        String idempotencyKey,

        @NotNull(message = "coffeeType is required")
        CoffeeType coffeeType,

        @NotNull(message = "price is required")
        @DecimalMin(value = "0.0", inclusive = false, message = "price must be greater than zero")
        @Digits(integer = 10, fraction = 2, message = "price may have at most 2 decimal places")
        BigDecimal price,

        @NotNull(message = "currency is required")
        @Pattern(regexp = "^[A-Z]{3}$", message = "currency must be a 3-letter ISO-4217 code, e.g. EUR")
        String currency,

        @NotNull(message = "loyaltyCardId is required")
        String loyaltyCardId
) {}
