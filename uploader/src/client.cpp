#include "uploader/client.hpp"

#include <httplib.h>
#include <nlohmann/json.hpp>

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
