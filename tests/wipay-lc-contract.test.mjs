import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import test from 'node:test';
import { assessLcBrowserReturn, createLcCheckout } from '../server/wipay-lc-contract.mjs';

const order = { id: 'pilot_0001', amountUsd: '50.00', currency: 'USD', providerEnvironment: 'sandbox' };
const developerId = '1';
const apiKey = '123'; // Published WiPay sandbox example only.
const hash = crypto.createHash('md5').update(order.id + order.amountUsd + apiKey).digest('hex');
const query = { order_id: order.id, total: order.amountUsd, status: 'success',
  responseCode: 'Y', transaction_id: '42-1-pilot_0001-20261027130102', hash, D: 'USD' };

test('LC sandbox posts only documented fields and keeps USD exact', () => {
  const checkout = createLcCheckout({ order, developerId, environment: 'sandbox',
    returnUrl: 'https://hub.v79sl.com/api/billing/wipay/return' });
  assert.equal(checkout.action, 'https://lca.wipayfinancial.com/v1/us_gateway');
  assert.deepEqual(checkout.fields, { developer_id: '1', total: '50.00',
    order_id: 'pilot_0001', return_url: 'https://hub.v79sl.com/api/billing/wipay/return' });
  assert.throws(() => createLcCheckout({ order: { ...order, amountUsd: '50' }, developerId,
    environment: 'sandbox', returnUrl: 'https://hub.v79sl.com/return' }));
  assert.throws(() => createLcCheckout({ order, developerId, environment: 'sandbox',
    returnUrl: 'http://hub.v79sl.com/return' }));
});

test('matching LC redirect remains provisional, never activates', () => {
  assert.deepEqual(assessLcBrowserReturn({ query, order, developerId, apiKey, environment: 'sandbox' }), {
    provisional: true, activate: false, reason: 'independent_confirmation_required',
    orderId: order.id, transactionId: query.transaction_id, amountUsd: '50.00',
  });
});

test('fail closed on tampering, conflicting identity, duplicates and environment', () => {
  for (const q of [
    { ...query, total: '49.99' }, { ...query, order_id: 'another' },
    { ...query, status: 'failed' }, { ...query, responseCode: 'N' },
    { ...query, hash: crypto.createHash('md5').update(query.transaction_id + order.amountUsd + apiKey).digest('hex') },
    { ...query, transaction_id: '42-2-pilot_0001-20261027130102' },
    { ...query, transaction_id: '42-1-another-20261027130102' },
    { ...query, D: 'XCD' }, { ...query, order_id: [order.id, order.id] },
  ]) assert.equal(assessLcBrowserReturn({ query: q, order, developerId, apiKey,
    environment: 'sandbox' }).activate, false);
  assert.equal(assessLcBrowserReturn({ query, order: { ...order, providerEnvironment: 'live' },
    developerId, apiKey, environment: 'sandbox' }).provisional, false);
});
