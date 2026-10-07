import test from "node:test";
import assert from "node:assert/strict";
import { createWipayCheckout, getWipayConfig, publicWipayConfig, signBillingOrderState, verifyWipayReturn } from "../server/wipay-provider.mjs";
import { wipayResponseHash } from "../server/billing-contract.mjs";

const secret = "0123456789abcdef0123456789abcdef";

test("sandbox can use documented WiPay test defaults without exposing secrets publicly", () => {
  const config = getWipayConfig({
    WIPAY_ENABLED: "1",
    WIPAY_ENV: "sandbox",
    APP_URL: "https://hub.example.com",
    V79_BILLING_STATE_SECRET: secret,
  });
  assert.equal(config.ready, true);
  assert.equal(config.accountNumber, "1234567890");
  assert.equal(config.apiKey, "123");
  assert.equal(config.currency, "TTD");
  const publicConfig = publicWipayConfig(config);
  assert.equal(publicConfig.ready, true);
  assert.equal("apiKey" in publicConfig, false);
  assert.equal("stateSecret" in publicConfig, false);
});

test("live mode refuses sandbox credentials", () => {
  const config = getWipayConfig({
    WIPAY_ENABLED: "1",
    WIPAY_ENV: "live",
    WIPAY_ACCOUNT_NUMBER: "1234567890",
    WIPAY_API_KEY: "123",
    WIPAY_PAYMENT_URL: "https://lca.example.com/pay",
    WIPAY_COUNTRY_CODE: "LC",
    WIPAY_CURRENCY: "XCD",
    WIPAY_RESPONSE_URL: "https://hub.example.com/api/billing/wipay/return",
    V79_BILLING_STATE_SECRET: secret,
  });
  assert.equal(config.ready, false);
  assert.match(config.problems.join(" "), /Sandbox WiPay credentials/);
});

test("checkout binds the order to V79 state and never sends the API key", () => {
  const config = getWipayConfig({
    WIPAY_ENABLED: "1",
    WIPAY_ENV: "sandbox",
    APP_URL: "https://hub.example.com",
    V79_BILLING_STATE_SECRET: secret,
  });
  const checkout = createWipayCheckout({
    order: { id: "order_123", amount: 29.99, currency: "TTD" },
    config,
  });
  assert.equal(checkout.fields.total, "29.99");
  assert.equal(checkout.fields.order_id, "order_123");
  assert.equal(checkout.fields.response_url, "https://hub.example.com/api/billing/wipay/return");
  assert.equal("api_key" in checkout.fields, false);
  const data = JSON.parse(checkout.fields.data);
  assert.equal(data.orderId, "order_123");
  assert.equal(data.state, signBillingOrderState({ orderId: "order_123", amount: 29.99, currency: "TTD", secret }));
});

test("verified return rejects order tampering even when the WiPay hash is valid", () => {
  const config = getWipayConfig({
    WIPAY_ENABLED: "1",
    WIPAY_ENV: "sandbox",
    APP_URL: "https://hub.example.com",
    V79_BILLING_STATE_SECRET: secret,
  });
  const order = { id: "order_123", amount: 29.99, currency: "TTD" };
  const checkout = createWipayCheckout({ order, config });
  const transactionId = "SB-12-1-order_123-20261007120000";
  const total = "29.99";
  const base = {
    status: "success",
    transaction_id: transactionId,
    total,
    currency: "TTD",
    hash: wipayResponseHash(transactionId, total, config.apiKey),
    data: checkout.fields.data,
  };
  assert.equal(verifyWipayReturn({ query: { ...base, order_id: order.id }, expectedOrder: order, config }).ok, true);
  assert.equal(verifyWipayReturn({ query: { ...base, order_id: "order_999" }, expectedOrder: order, config }).reason, "order_mismatch");
  assert.equal(verifyWipayReturn({ query: { ...base, order_id: order.id, total: "39.99", hash: wipayResponseHash(transactionId, "39.99", config.apiKey) }, expectedOrder: order, config }).reason, "amount_mismatch");
});
