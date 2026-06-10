#pragma once
#include "payment.hpp"
#include <optional>
#include <string>
#include <vector>

struct ParseResult {
    std::optional<Payment> result;
    std::string error;
};

class Parser {
  public:
    Parser(const std::string &csvPath);
    static ParseResult parseString(const std::vector<std::string> &row);

    size_t getSizeRow() const { return row.size(); }
    const std::vector<Payment> &getPayments() const { return row; }

  private:
    std::vector<Payment> row;
};
