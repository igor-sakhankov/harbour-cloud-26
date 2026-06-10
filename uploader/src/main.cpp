#include <iostream>
#include <string>

#include "uploader/parser.hpp"
#include "uploader/client.hpp"

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <csv-path>\n";
        return 1;
    }

    const std::string csvPath = argv[1];
    Parser parser(csvPath);
    
    std::cout << "parsed " << parser.getSizeRow() << "\n";

    const auto& payments = parser.getPayments();
    if (payments.empty()) {
        std::cerr << "no valid payments to send\n";
        return 1;
    }
    
    SendResult res = sendPayment("http://127.0.0.1:8090", payments[0]);
    if (res.responded) {
        std::cout << "sent payment 0 -> HTTP " << res.status << "\n";
    } else {
        std::cout << "send failed: " << res.error << "\n";
    }
    
    return 0;
}
