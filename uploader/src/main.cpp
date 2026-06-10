#include <iostream>
#include <string>

#include "uploader/client.hpp"
#include "uploader/parser.hpp"

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <csv-path>\n";
        return 1;
    }

    const std::string csvPath = argv[1];
    Parser parser(csvPath);

    std::cout << "parsed " << parser.getSizeRow() << "\n";

    const auto &payments = parser.getPayments();
    if (payments.empty()) {
        std::cerr << "no valid payments to send\n";
        return 1;
    }

    const std::string baseUrl = "http://127.0.0.1:8080";

    int created = 0, duplicate = 0, rejected = 0, failed = 0;

    for (size_t i = 0; i < payments.size(); ++i) {
        const Payment &p = payments[i];
        SendResult res = sendPayment(baseUrl, p);

        if (!res.responded) {
            ++failed;
            std::cout << "FAILED    " << p.transactionId << " -> " << res.error << "\n ";
        } else if (res.status == 201) {
            ++created;
            std::cout << "CREATED   " << p.transactionId << "\n";
        } else if (res.status == 200) {
            ++duplicate;
            std::cout << "DUPLICATE " << p.transactionId << "\n";
        } else {
            ++rejected;
            std::cout << "REJECTED  " << p.transactionId << " -> HTTP " << res.status << "\n";
        }
    }

    std::cout << "\nSummary: created=" << created << " duplicate=" << duplicate << " rejected=" << rejected << " failed=" << failed << "\n";
    return 0;
}
