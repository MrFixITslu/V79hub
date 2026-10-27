import crypto from 'node:crypto';

const SANDBOX = 'https://lca.wipayfinancial.com/v1/us_gateway';
const LIVE = 'https://lca.wipayfinancial.com/v1/us_gateway_live';
const ORDER_ID = /^[A-Za-z0-9_-]{1,16}$/;
const USD = /^(?:0|[1-9][0-9]*)\.[0-9]{2}$/;

function equalHex(a, b) {
  if (!/^[a-f0-9]{32}$/i.test(a) || !/^[a-f0-9]{32}$/i.test(b)) return false;
  return crypto.timingSafeEqual(Buffer.from(a, 'hex'), Buffer.from(b, 'hex'));
}

function singleton(query, key) {
  const value = query?.[key];
  return typeof value === 'string' ? value : null;
}

export function createLcCheckout({ order, developerId, environment, returnUrl }) {
  if (!ORDER_ID.test(order?.id ?? '') || !USD.test(order?.amountUsd ?? '') || order.amountUsd === '0.00')
    throw new Error('Persist a positive two-decimal USD amount and unique LC order ID first.');
  if (order.currency !== 'USD' || order.providerEnvironment !== environment)
    throw new Error('Order currency/environment mismatch.');
  if (!/^[1-9][0-9]{0,4}$/.test(String(developerId)) || (environment === 'sandbox' && String(developerId) !== '1'))
    throw new Error('Invalid LC developer ID.');
  if (environment !== 'sandbox' && environment !== 'live') throw new Error('Invalid LC environment.');
  const url = new URL(returnUrl);
  if (url.protocol !== 'https:' || url.username || url.password) throw new Error('HTTPS return URL required.');
  return {
    action: environment === 'live' ? LIVE : SANDBOX,
    method: 'POST',
    contentType: 'application/x-www-form-urlencoded',
    fields: { developer_id: String(developerId), total: order.amountUsd, order_id: order.id, return_url: url.href },
  };
}

// The LC v1.0.1 hash authenticates only order_id and total. It does not bind
// status, transaction ID, merchant, currency or settlement. Never grant access
// from this result; independent provider confirmation is mandatory.
export function assessLcBrowserReturn({ query, order, developerId, apiKey, environment }) {
  const no = reason => ({ provisional: false, activate: false, reason });
  if (!query || !order || !apiKey || !ORDER_ID.test(order.id ?? '') ||
      !USD.test(order.amountUsd ?? '') || order.currency !== 'USD' ||
      order.providerEnvironment !== environment || !['sandbox', 'live'].includes(environment))
    return no('invalid_order_or_environment');
  const id = singleton(query, 'order_id');
  const total = singleton(query, 'total');
  const status = singleton(query, 'status');
  const response = singleton(query, 'responseCode');
  const tx = singleton(query, 'transaction_id');
  const hash = singleton(query, 'hash');
  const currency = singleton(query, 'D');
  if (id !== order.id || total !== order.amountUsd) return no('order_or_amount_mismatch');
  if (status !== 'success' || response !== 'Y') return no('not_approved');
  if (!/^[1-9][0-9]{0,4}$/.test(String(developerId))) return no('merchant_mismatch');
  const escapedId = id.replace(/[.*+?^$\{\}()|[\]\\]/g, '\\$&');
  const txPattern = new RegExp('^(?:100|[1-9]?[0-9])-' + developerId + '-' + escapedId + '-[0-9]{14}$');
  if (!tx || !txPattern.test(tx)) return no('transaction_identity_mismatch');
  if (currency !== null && currency !== 'USD') return no('currency_mismatch');
  const expected = crypto.createHash('md5').update(id + order.amountUsd + apiKey).digest('hex');
  if (!hash || !equalHex(hash, expected)) return no('hash_mismatch');
  return { provisional: true, activate: false, reason: 'independent_confirmation_required',
    orderId: id, transactionId: tx, amountUsd: total };
}
