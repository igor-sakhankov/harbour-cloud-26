#include <algorithm>
#include <cctype>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>
#include <vector>

#include "uploader/parser.hpp"

Parser::Parser(const std::string &csvPath) {
    std::ifstream file(csvPath);
    if (!file.is_open()) {
        std::cerr << "Could not open " << csvPath << "\n";
        return;
    }

    std::string line;
    size_t idx = 0;
    while (std::getline(file, line)) {
        std::stringstream ss(line);
        std::string cell;
        std::vector<std::string> oneRow;

        while (std::getline(ss, cell, ',')) {
            oneRow.push_back(cell);
        }

        ParseResult res = parseString(oneRow);

        ++idx;
        if (!res.error.empty()) {
            std::cerr << "line " << idx << ": " << res.error << "\n";
        } else {
            row.push_back(res.result.value());
        }
    }
}

static std::optional<CoffeeType> parseCoffeeType(const std::string &s) {
    if (s == "ESPRESSO")
        return CoffeeType::Espresso;
    if (s == "LATTE")
        return CoffeeType::Latte;
    if (s == "CAPPUCCINO")
        return CoffeeType::Cappuccino;
    if (s == "AMERICANO")
        return CoffeeType::Americano;
    if (s == "FLAT_WHITE")
        return CoffeeType::FlatWhite;
    return std::nullopt;
}

static std::string trim(const std::string &s) {
    const auto first = s.find_first_not_of(" \t\r");
    if (first == std::string::npos)
        return "";
    const auto last = s.find_last_not_of(" \t\r");
    return s.substr(first, last - first + 1);
}

static bool isValidPriceFormat(const std::string &s) {
    if (s.empty())
        return false;
    int dots = 0;
    int digitsAfterDot = 0;
    for (char c : s) {
        if (c == '.') {
            if (++dots > 1)
                return false;
        } else if (!std::isdigit(static_cast<unsigned char>(c))) {
            return false;
        } else if (dots == 1) {
            ++digitsAfterDot;
        }
    }
    if (dots == 1 && (digitsAfterDot == 0 || digitsAfterDot > 2))
        return false;
    return s != ".";
}

ParseResult Parser::parseString(const std::vector<std::string> &row) {
    if (row.size() != 6) {
        return {std::nullopt, "expected 6 fields, got " + std::to_string(row.size())};
    }

    const std::string storeId = trim(row[0]);
    const std::string transactionId = trim(row[1]);
    const std::string coffeeType = trim(row[2]);
    const std::string priceStr = trim(row[3]);
    const std::string currency = trim(row[4]);
    const std::string loyaltyCardId = trim(row[5]);

    if (storeId.empty())
        return {std::nullopt, "storeId is blank"};
    if (transactionId.empty())
        return {std::nullopt, "transactionId is blank"};
    if (loyaltyCardId.empty())
        return {std::nullopt, "loyaltyCardId is blank"};

    const auto coffee = parseCoffeeType(coffeeType);
    if (!coffee) {
        return {std::nullopt, "unknown coffeeType: '" + coffeeType + "'"};
    }

    if (!isValidPriceFormat(priceStr)) {
        return {std::nullopt, "invalid price format: '" + priceStr + "'"};
    }
    const double price = std::stod(priceStr);
    if (price <= 0) {
        return {std::nullopt, "price must be > 0, got " + priceStr};
    }

    if (currency.size() != 3 || !std::all_of(currency.begin(), currency.end(),
                                             [](unsigned char c) { return std::isupper(c); })) {
        return {std::nullopt, "currency must be 3 uppercase letters: '" + currency + "'"};
    }

    return {Payment{storeId, transactionId, coffeeType, price, currency, loyaltyCardId}, ""};
}
