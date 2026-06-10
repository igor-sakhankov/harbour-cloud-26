// storeId, transactionId,coffeeType,price,currency,loyaltyCardId
#include <optional>
#include <string>

enum class CoffeeType { Espresso, Latte, Cappuccino, Americano, FlatWhite };
static std::optional<CoffeeType> parseCoffeeType(const std::string &s);

struct Payment {
    const std::string storeId;
    const std::string transactionId;
    const std::string coffeeType;
    const double price = 0.0;
    const std::string currency;
    const std::string loyaltyCardId;
};
