"""Opt-in, bounded live API check during an explicitly requested preview build.

No customer information, orders, shipment bookings or payment calls are involved.
This is a synthetic 1 kg quote, not a furniture shipping price.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from rajaongkir_shipping import _NoRedirect, calculate_rates, ShippingUnavailable


def search_location(key, search):
    query = urllib.parse.urlencode({'search': search, 'limit': 50, 'offset': 0})
    req = urllib.request.Request(
        'https://rajaongkir.komerce.id/api/v1/destination/domestic-destination?' + query,
        headers={'key': key, 'Accept': 'application/json'})
    with urllib.request.build_opener(_NoRedirect()).open(req, timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ShippingUnavailable('provider_response_invalid')
    result = json.loads(raw)
    if result.get('meta', {}).get('code') != 200 or not isinstance(result.get('data'), list):
        raise ShippingUnavailable('location_lookup_failed')
    return result['data']


def run():
    if os.getenv('RAJAONGKIR_RUN_BUILD_PROBE') != '1':
        print('RAJAONGKIR_PROBE_SKIPPED')
        return 0
    key = os.getenv('RAJAONGKIR_API_KEY', '').strip()
    if not key:
        print('RAJAONGKIR_PROBE_FAILED provider_not_configured')
        return 1
    try:
        origins = search_location(key, 'Ngasinan')
        origins = [x for x in origins if 'PONOROGO' in str(x.get('city_name', '')).upper()
                   and str(x.get('district_name', '')).upper() == 'JETIS'
                   and str(x.get('subdistrict_name', '')).upper() == 'NGASINAN']
        if len(origins) != 1:
            print('RAJAONGKIR_PROBE_FAILED origin_not_uniquely_resolved')
            return 1
        destinations = search_location(key, 'Surabaya')
        destinations = [x for x in destinations if 'SURABAYA' in str(x.get('city_name', '')).upper()]
        if not destinations:
            print('RAJAONGKIR_PROBE_FAILED test_destination_unavailable')
            return 1
        rates = calculate_rates(api_key=key, origin_id=origins[0]['id'],
                                destination_id=destinations[0]['id'], weight_grams=1000,
                                couriers=['jne'])
        print('RAJAONGKIR_PROBE_OK ' + json.dumps({
            'synthetic_package_grams': 1000, 'service_count': len(rates),
            'rates': [dict(courier=r.courier, service=r.service, cost_idr=r.cost_idr,
                           estimated_days=r.estimated_days) for r in rates]}, ensure_ascii=True))
        return 0
    except urllib.error.HTTPError as exc:
        raw = exc.read(8192)
        content_type = exc.headers.get('Content-Type', '').split(';')[0]
        category = 'unknown'
        try:
            payload = json.loads(raw)
            message = json.dumps(payload, ensure_ascii=True).lower()
            safe_message = re.sub(r'[A-Za-z0-9_+/=-]{24,}', '[redacted]', message.replace(key.lower(), '[redacted]'))[:240]
            print('RAJAONGKIR_PROVIDER_REASON ' + safe_message)
            if any(x in message for x in ('invalid', 'api key', 'apikey', 'unauthorized')):
                category = 'authentication'
            elif any(x in message for x in ('quota', 'limit', 'subscription', 'plan')):
                category = 'account_limit'
            else:
                category = 'provider_json_error'
        except (ValueError, AttributeError):
            if any(x in raw.lower() for x in (b'cloudflare', b'challenge', b'just a moment')):
                category = 'edge_security'
            elif b'forbidden' in raw.lower():
                category = 'access_denied'
        print('RAJAONGKIR_PROBE_FAILED ' + json.dumps({
            'http_status': exc.code, 'content_type': content_type,
            'category': category}))
        return 1
    except Exception as exc:
        # Never log keys, credentials, headers, request dumps or provider bodies.
        print('RAJAONGKIR_PROBE_FAILED ' + type(exc).__name__)
        return 1


if __name__ == '__main__':
    sys.exit(run())
