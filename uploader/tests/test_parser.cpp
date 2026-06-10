#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <doctest/doctest.h>

#include "uploader/parser.hpp"

static std::vector<std::string> goodRow() {
    return {"store-london-01", "txn-0001", "LATTE", "3.50", "EUR", "card-1001"};
}

TEST_CASE("a valid row parses into a Payment") {
    ParseResult r = Parser::parseString(goodRow());

    CHECK(r.error.empty());
    REQUIRE(r.result.has_value());
    CHECK(r.result->storeId == "store-london-01");
    CHECK(r.result->transactionId == "txn-0001");
    CHECK(r.result->coffeeType == "LATTE");
    CHECK(r.result->price == doctest::Approx(3.50));
    CHECK(r.result->currency == "EUR");
    CHECK(r.result->loyaltyCardId == "card-1001");
}

TEST_CASE("surrounding whitespace is trimmed") {
    ParseResult r = Parser::parseString(
        {" store-1 ", " txn-1 ", " LATTE ", " 3.50 ", " EUR ", " card-1 "});
    REQUIRE(r.result.has_value());
    CHECK(r.result->storeId == "store-1");
    CHECK(r.result->currency == "EUR");
}

TEST_CASE("wrong number of fields is rejected") {
    SUBCASE("too few") {
        ParseResult r = Parser::parseString({"store-1", "txn-1", "LATTE"});
        CHECK_FALSE(r.result.has_value());
        CHECK_FALSE(r.error.empty());
    }
    SUBCASE("too many") {
        ParseResult r = Parser::parseString(
            {"store-1", "txn-1", "LATTE", "3.50", "EUR", "card-1", "extra"});
        CHECK_FALSE(r.result.has_value());
    }
}

TEST_CASE("blank required fields are rejected") {
    SUBCASE("blank storeId") {
        auto row = goodRow();
        row[0] = "";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
    SUBCASE("blank transactionId") {
        auto row = goodRow();
        row[1] = "";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
    SUBCASE("blank loyaltyCardId") {
        auto row = goodRow();
        row[5] = "";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
}

TEST_CASE("unknown coffee type is rejected") {
    auto row = goodRow();
    row[2] = "TEA";
    ParseResult r = Parser::parseString(row);
    CHECK_FALSE(r.result.has_value());
    CHECK(r.error.find("coffeeType") != std::string::npos);
}

TEST_CASE("invalid prices are rejected") {
    SUBCASE("zero") {
        auto row = goodRow();
        row[3] = "0.00";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
    SUBCASE("non-numeric") {
        auto row = goodRow();
        row[3] = "abc";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
    SUBCASE("too many decimal places") {
        auto row = goodRow();
        row[3] = "3.555";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
    SUBCASE("negative") {
        auto row = goodRow();
        row[3] = "-3.50";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
}

TEST_CASE("invalid currency is rejected") {
    SUBCASE("lowercase") {
        auto row = goodRow();
        row[4] = "eur";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
    SUBCASE("wrong length") {
        auto row = goodRow();
        row[4] = "EURO";
        CHECK_FALSE(Parser::parseString(row).result.has_value());
    }
}
