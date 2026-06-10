#pragma once
#include "uploader/payment.hpp"
#include <string>

struct SendResult {
    bool responded = false;
    int status = 0;
    std::string error;
    int attempts = 0;
};

SendResult sendPayment(const std::string &baseUrl, const Payment &payment);
SendResult sendWithRetry(const std::string &baseUrl, const Payment &payment, int maxAttempts = 5,
                         int baseDelayMs = 200);
