#pragma once
#include "uploader/payment.hpp"
#include <string>

struct SendResult {
    bool responded = false;
    int status = 0;
    std::string error;
};

SendResult sendPayment(const std::string& baseUrl, const Payment& payment);
