"""Server-side RajaOngkir Shipping Cost adapter; no checkout route is enabled.

Only validated Odoo order data may be supplied by the eventual checkout bridge.
Never accept a customer-supplied weight, price, origin or courier allowlist.
"""
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING

ENDPOINT = 'https://rajaongkir.komerce.id/api/v1/calculate/domestic-cost'
MAX_RESPONSE_BYTES = 1_000_000


class ShippingUnavailable(Exception):
    """A quote is unavailable; callers must never substitute a zero price."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _post(form, api_key):
    request = urllib.request.Request(
        ENDPOINT, data=urllib.parse.urlencode(form).encode('ascii'),
        headers={'key': api_key, 'Content-Type': 'application/x-www-form-urlencoded',
                 'Accept': 'application/json'}, method='POST')
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=10) as reply:
            body = reply.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ShippingUnavailable('provider_response_invalid')
        return json.loads(body)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # Do not copy request headers, API keys, URLs or provider bodies to logs.
        raise ShippingUnavailable('provider_unavailable') from None


def _positive_id(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ShippingUnavailable('destination_not_verified')
    return value


def packed_weight_grams(lines):
    """Sum packed kilograms * quantity, rounding total up to whole grams.

The bridge must supply only physical order lines from company 6 / website 7.
Each line needs explicit verified packed weight, quantity, and courier eligibility.
Service and delivery lines must be excluded by the bridge, not treated as 0 kg.
"""
    if not lines:
        raise ShippingUnavailable('empty_shipment')
    total = Decimal('0')
    for line in lines:
        if line.get('packing_verified') is not True:
            raise ShippingUnavailable('packing_not_verified')
        if line.get('courier_eligible') is not True:
            raise ShippingUnavailable('manual_cargo_required')
        try:
            if isinstance(line['packed_weight_kg'], bool) or isinstance(line['quantity'], bool):
                raise ValueError()
            weight = Decimal(str(line['packed_weight_kg']))
            quantity = Decimal(str(line['quantity']))
            if not weight.is_finite() or not quantity.is_finite() or weight <= 0 or quantity <= 0:
                raise ValueError()
        except (KeyError, InvalidOperation, ValueError):
            raise ShippingUnavailable('packing_not_verified') from None
        total += weight * quantity * 1000
    if not total.is_finite() or total > 1_000_000_000:
        raise ShippingUnavailable('shipment_too_large')
    return int(total.to_integral_value(rounding=ROUND_CEILING))


@dataclass(frozen=True)
class Rate:
    courier: str
    service: str
    description: str
    cost_idr: int
    estimated_days: str


def calculate_rates(*, api_key, origin_id, destination_id, weight_grams,
                    couriers, post=_post):
    """Return provider quotes, not guaranteed final furniture freight prices.

RajaOngkir destination IDs must come from its search API, never Odoo record IDs.
"""
    if not isinstance(api_key, str) or not api_key.strip():
        raise ShippingUnavailable('provider_not_configured')
    _positive_id(origin_id)
    _positive_id(destination_id)
    if isinstance(weight_grams, bool) or not isinstance(weight_grams, int) or weight_grams < 1:
        raise ShippingUnavailable('packing_not_verified')
    if not couriers or not isinstance(couriers, (list, tuple)):
        raise ShippingUnavailable('courier_not_configured')
    if any(not isinstance(c, str) or not c.isascii() or not c.isalnum() for c in couriers):
        raise ShippingUnavailable('courier_not_configured')
    form = {'origin': origin_id, 'destination': destination_id,
            'weight': weight_grams, 'courier': ':'.join(couriers), 'price': 'lowest'}
    payload = post(form, api_key)
    if not isinstance(payload, dict):
        raise ShippingUnavailable('provider_response_invalid')
    meta = payload.get('meta')
    if not isinstance(meta, dict) or type(meta.get('code')) is not int or meta['code'] != 200:
        raise ShippingUnavailable('provider_unavailable')
    rows = payload.get('data')
    if not isinstance(rows, list):
        raise ShippingUnavailable('provider_response_invalid')
    rates = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cost, courier, service = row.get('cost'), row.get('code'), row.get('service')
        if (isinstance(cost, bool) or not isinstance(cost, (int, float))
                or not math.isfinite(cost) or cost <= 0 or cost != int(cost)
                or courier not in couriers or not isinstance(service, str) or not service.strip()):
            continue
        key = (courier, service)
        if key in rates:
            # Ambiguous duplicated service prices must not be silently chosen.
            raise ShippingUnavailable('provider_response_invalid')
        rates[key] = Rate(courier, service[:100], str(row.get('description', ''))[:250],
                          int(cost), str(row.get('etd', ''))[:100])
    if not rates:
        raise ShippingUnavailable('no_valid_service')
    return sorted(rates.values(), key=lambda r: (r.cost_idr, r.courier, r.service))
