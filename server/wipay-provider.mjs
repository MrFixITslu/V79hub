import crypto from "node:crypto";
import { normalizeMoney, verifyWipayResponse } from "./billing-contract.mjs";

const SANDBOX_DEFAULTS = Object.freeze({
  accountNumber: "1234567890",
  apiKey: "123",
  endpoint: "https://tt.wipayfinancial.com/plugins/payments/request",
  countryCode: "TT",
  currency: "TTD",
});

function clean(value) {
  return String(value || "").trim();
}

function safeEqualHex(leftValue, rightValue) {
  try {
    const left = Buffer.from(clean(leftValue).toLowerCase(), "hex");
    const right = Buffer.from(clean(rightValue).toLowerCase(), "hex");
    return left.length > 0 && left.length === right.length && crypto.timingSafeEqual(left, right);
  } catch {
    return false;
  }
}

export function billingStateSecret(env = process.env) {
  return clean(env.V79_BILLING_STATE_SECRET || env.V79_HUB_SECURITY_KEY || env.V79_PLATFORM_SHARED_SECRET);
}

export function getWipayConfig(env = process.env) {
  const environment = clean(env.WIPAY_ENV).toLowerCase() === "live" ? "live" : "sandbox";
  const enabled = clean(env.WIPAY_ENABLED) === "1";
  const useSandboxDefaults = environment === "sandbox" && clean(env.WIPAY_SANDBOX_DOC_DEFAULTS) !== "0";

  const accountNumber = clean(env.WIPAY_ACCOUNT_NUMBER) || (useSandboxDefaults ? SANDBOX_DEFAULTS.accountNumber : "");
  const apiKey = clean(env.WIPAY_API_KEY) || (useSandboxDefaults ? SANDBOX_DEFAULTS.apiKey : "");
  const endpoint = clean(env.WIPAY_PAYMENT_URL) || (useSandboxDefaults ? SANDBOX_DEFAULTS.endpoint : "");
  const countryCode = (clean(env.WIPAY_COUNTRY_CODE) || (useSandboxDefaults ? SANDBOX_DEFAULTS.countryCode : "")).toUpperCase();
  const currency = (clean(env.WIPAY_CURRENCY) || (useSandboxDefaults ? SANDBOX_DEFAULTS.currency : "")).toUpperCase();
  const feeStructure = clean(env.WIPAY_FEE_STRUCTURE) || "merchant_absorb";
  const appUrl = clean(env.APP_URL).replace(/\/$/, "");
  const responseUrl = clean(env.WIPAY_RESPONSE_URL) || (appUrl ? `${appUrl}/api/billing/wipay/return` : "");
  const stateSecret = billingStateSecret(env);
  const problems = [];

  if (enabled) {
    if (!accountNumber) problems.push("WIPAY_ACCOUNT_NUMBER is required.");
    if (!apiKey) problems.push("WIPAY_API_KEY is required.");
    if (!/^https:\/\//i.test(endpoint)) problems.push("WIPAY_PAYMENT_URL must be an HTTPS URL.");
    if (!/^[A-Z]{2,4}$/.test(countryCode)) problems.push("WIPAY_COUNTRY_CODE is required.");
    if (!/^[A-Z]{3}$/.test(currency)) problems.push("WIPAY_CURRENCY is required.");
    if (!/^https:\/\//i.test(responseUrl)) problems.push("WIPAY_RESPONSE_URL or APP_URL must resolve to HTTPS.");
    if (stateSecret.length < 32) problems.push("V79_BILLING_STATE_SECRET (or a secure Hub fallback key) must be at least 32 characters.");
    if (feeStructure !== "merchant_absorb") problems.push("V79 Billing v1 requires WIPAY_FEE_STRUCTURE=merchant_absorb for exact amount verification.");
    if (environment === "live" && (accountNumber === SANDBOX_DEFAULTS.accountNumber || apiKey === SANDBOX_DEFAULTS.apiKey)) {
      problems.push("Sandbox WiPay credentials cannot be used in live mode.");
    }
  }

  return {
    provider: "wipay",
    enabled,
    ready: enabled && problems.length === 0,
    environment,
    accountNumber,
    apiKey,
    endpoint,
    countryCode,
    currency,
    feeStructure,
    responseUrl,
    stateSecret,
    sandboxDocumentationDefaults: useSandboxDefaults,
    problems,
  };
}

export function publicWipayConfig(config) {
  return {
    provider: "wipay",
    enabled: Boolean(config.enabled),
    ready: Boolean(config.ready),
    environment: config.environment,
    countryCode: config.countryCode,
    currency: config.currency,
    feeStructure: config.feeStructure,
    endpointConfigured: Boolean(config.endpoint),
    accountConfigured: Boolean(config.accountNumber),
    sandboxDocumentationDefaults: Boolean(config.sandboxDocumentationDefaults),
    problems: Array.isArray(config.problems) ? [...config.problems] : [],
  };
}

export function signBillingOrderState({ orderId, amount, currency, secret }) {
  const normalized = normalizeMoney(amount);
  if (!orderId || normalized === null || !/^[A-Z]{3}$/.test(String(currency || "").toUpperCase()) || String(secret || "").length < 32) {
    throw new Error("Valid billing order state inputs are required.");
  }
  const payload = [String(orderId), normalized.toFixed(2), String(currency).toUpperCase()].join("\n");
  return crypto.createHmac("sha256", String(secret)).update(payload).digest("hex");
}

export function createWipayCheckout({ order, config }) {
  if (!config?.ready) throw new Error("WiPay is not ready.");
  const amount = normalizeMoney(order?.amount);
  if (!order?.id || amount === null || amount <= 0) throw new Error("A valid positive billing order is required.");
  if (String(order.currency || "").toUpperCase() !== config.currency) throw new Error("Billing order currency does not match WiPay configuration.");

  const state = signBillingOrderState({
    orderId: order.id,
    amount,
    currency: config.currency,
    secret: config.stateSecret,
  });

  return {
    provider: "wipay",
    environment: config.environment,
    action: config.endpoint,
    method: "POST",
    fields: {
      account_number: config.accountNumber,
      avs: "0",
      country_code: config.countryCode,
      currency: config.currency,
      data: JSON.stringify({
        v: 1,
        orderId: order.id,
        amount: amount.toFixed(2),
        currency: config.currency,
        state,
      }),
      environment: config.environment,
      fee_structure: config.feeStructure,
      method: "credit_card",
      order_id: order.id,
      origin: "V79-Hub",
      response_url: config.responseUrl,
      total: amount.toFixed(2),
    },
  };
}

export function verifyWipayReturn({ query, expectedOrder, config }) {
  const status = clean(query?.status).toLowerCase();
  const transactionId = clean(query?.transaction_id);
  const orderId = clean(query?.order_id);
  const totalRaw = clean(query?.total);
  const hash = clean(query?.hash);
  const currency = clean(query?.currency).toUpperCase();
  const amount = normalizeMoney(totalRaw);
  const expectedAmount = normalizeMoney(expectedOrder?.amount);

  if (!config?.ready) return { ok: false, reason: "wipay_not_ready", status, transactionId, orderId };
  if (status !== "success") return { ok: false, reason: "provider_status_not_success", status, transactionId, orderId };
  if (!verifyWipayResponse({ transactionId, total: totalRaw, apiKey: config.apiKey, hash })) {
    return { ok: false, reason: "provider_hash_invalid", status, transactionId, orderId };
  }
  if (!expectedOrder?.id || orderId !== expectedOrder.id) {
    return { ok: false, reason: "order_mismatch", status, transactionId, orderId };
  }
  if (currency !== config.currency || currency !== String(expectedOrder.currency || "").toUpperCase()) {
    return { ok: false, reason: "currency_mismatch", status, transactionId, orderId };
  }
  if (amount === null || expectedAmount === null || amount !== expectedAmount) {
    return { ok: false, reason: "amount_mismatch", status, transactionId, orderId };
  }

  let data;
  try {
    data = typeof query?.data === "string" ? JSON.parse(query.data) : query?.data;
  } catch {
    return { ok: false, reason: "state_data_invalid", status, transactionId, orderId };
  }

  const expectedState = signBillingOrderState({
    orderId: expectedOrder.id,
    amount: expectedAmount,
    currency,
    secret: config.stateSecret,
  });
  if (!data || data.orderId !== expectedOrder.id || data.amount !== expectedAmount.toFixed(2) || data.currency !== currency || !safeEqualHex(data.state, expectedState)) {
    return { ok: false, reason: "state_signature_invalid", status, transactionId, orderId };
  }

  return {
    ok: true,
    reason: "verified",
    status,
    transactionId,
    orderId,
    amount,
    currency,
    message: clean(query?.message).slice(0, 300),
    date: clean(query?.date).slice(0, 40),
  };
}
