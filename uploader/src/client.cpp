#include "uploader/client.hpp"

#include <httplib.h>
#include <nlohmann/json.hpp>
#include <thread>

SendResult sendPayment(const std::string &baseUrl, const Payment &p) {
    nlohmann::json body;
    body["coffeeType"] = p.coffeeType;
    body["price"] = p.price;
    body["currency"] = p.currency;
    body["loyaltyCardId"] = p.loyaltyCardId;

    httplib::Client client(baseUrl);
    httplib::Headers headers = {
        {"Store-Id", p.storeId},
        {"Idempotency-Key", p.transactionId},
    };

    httplib::Result res = client.Post("/api/v1/payments", headers, body.dump(), "application/json");
    SendResult out;

    if (res) {
        out.responded = true;
        out.status = res->status;
    } else {
        out.error = "transport error: " + httplib::to_string(res.error());
    }

    return out;
}

SendResult sendWithRetry(const std::string &baseUrl, const Payment &payment, int maxAttempts,
                         int baseDelayMs) {
    SendResult res;
    for (size_t attempt = 0; attempt < maxAttempts; ++attempt) {
        res = sendPayment(baseUrl, payment);
        bool retryable =
            !res.responded || res.status == 429 || (res.status >= 500 && res.status <= 599);

        if (!retryable) {
            return res;
        }

        if (attempt + 1 < maxAttempts) {
            int delay = std::min(baseDelayMs * (1 << attempt), 5000);
            std::this_thread::sleep_for(std::chrono::milliseconds(delay));
        }
    }
    return res;
}
