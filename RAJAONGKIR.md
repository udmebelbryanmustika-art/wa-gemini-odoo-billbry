# RajaOngkir Shipping Cost adapter

Preparation only: this adapter does not register an HTTP route or activate checkout.
No credentials or deployment-specific configuration are included.

`packed_weight_grams(lines)` requires verified packed kilograms, quantity and explicit courier eligibility. Missing, zero, non-finite or negative data is rejected.

`calculate_rates` calls the official Shipping Cost endpoint with a server-side key, verified provider location IDs, positive grams and a configured courier allowlist. Invalid or zero returned prices are rejected rather than displayed as free delivery. Live calls must use a durable request budget and caching before exposing an endpoint to visitors.

Before checkout use, implement authenticated server-side order access, server-derived packing data, quote expiration, atomic delivery-price application and invalidation on address or cart changes. Do not trust client-supplied weights or prices. Handle unsupported furniture freight with a manual quotation. Returned quotes remain provider estimates subject to service constraints.

Keep API keys in server-only secret variables, never in browser bundles, QWeb, logs or source control.

Run `python -m unittest test_rajaongkir_shipping -v`. Tests use a mocked transport and dummy key. No live-provider validation is implied.

Official reference: https://rajaongkir.com/docs/shipping-cost/endpoint-rajaongkir-for-search-base/calculate-domestic-cost
