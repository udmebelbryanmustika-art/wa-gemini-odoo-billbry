import unittest
from rajaongkir_shipping import ShippingUnavailable, packed_weight_grams, calculate_rates


class ShippingTests(unittest.TestCase):
    def line(self, weight='1.25', quantity=2, **extra):
        return dict(packing_verified=True, courier_eligible=True,
                    packed_weight_kg=weight, quantity=quantity, **extra)

    def test_weight_quantity_and_rounding(self):
        self.assertEqual(packed_weight_grams([self.line()]), 2500)
        self.assertEqual(packed_weight_grams([self.line('0.0001', 1)]), 1)
        self.assertEqual(packed_weight_grams([self.line(), self.line('0.5', 1)]), 3000)

    def test_invalid_weights_rejected(self):
        for weight in [0, -1, '', None, 'NaN', 'Infinity', True]:
            with self.subTest(weight=weight), self.assertRaises(ShippingUnavailable):
                packed_weight_grams([self.line(weight)])

    def test_invalid_quantities_rejected(self):
        for quantity in [0, -1, '', None, 'NaN', 'Infinity', True]:
            with self.subTest(quantity=quantity), self.assertRaises(ShippingUnavailable):
                packed_weight_grams([self.line(quantity=quantity)])

    def test_empty_unverified_cargo_rejected(self):
        for lines in [[], [dict(self.line(), packing_verified=False)],
                      [dict(self.line(), courier_eligible=False)], [{}]]:
            with self.subTest(lines=lines), self.assertRaises(ShippingUnavailable):
                packed_weight_grams(lines)

    def request(self, response, **extra):
        def post(form, key):
            self.assertEqual(key, 'TEST_ONLY_NOT_A_REAL_KEY')
            self.assertEqual(form, {'origin': 1, 'destination': 2, 'weight': 2500,
                                    'courier': 'jne:jnt', 'price': 'lowest'})
            return response
        args = dict(api_key='TEST_ONLY_NOT_A_REAL_KEY', origin_id=1, destination_id=2,
                    weight_grams=2500, couriers=['jne', 'jnt'], post=post)
        args.update(extra)
        return calculate_rates(**args)

    def good(self, rows=None):
        return {'meta': {'code': 200}, 'data': rows if rows is not None else [
            {'code': 'jne', 'service': 'REG', 'cost': 25000, 'etd': '2-3'}]}

    def test_rates_and_transport_contract(self):
        rates = self.request(self.good())
        self.assertEqual(rates[0].cost_idr, 25000)
        self.assertEqual(rates[0].estimated_days, '2-3')

    def test_zero_or_untrusted_prices_not_free(self):
        for cost in [0, -1, True, '25000', float('nan'), 1.5]:
            with self.subTest(cost=cost), self.assertRaises(ShippingUnavailable):
                self.request(self.good([{'code': 'jne', 'service': 'REG', 'cost': cost}]))

    def test_bad_responses_rejected(self):
        for response in [None, [], {}, {'meta': {'code': 429}}, self.good([]),
                         {'meta': {'code': 200}, 'data': None},
                         self.good([{'code': 'other', 'service': 'REG', 'cost': 1}])]:
            with self.subTest(response=response), self.assertRaises(ShippingUnavailable):
                self.request(response)

    def test_duplicate_service_rejected(self):
        row = {'code': 'jne', 'service': 'REG', 'cost': 25000}
        with self.assertRaises(ShippingUnavailable):
            self.request(self.good([row, row]))

    def test_bad_requests_rejected_before_transport(self):
        for extra in [dict(api_key=''), dict(origin_id=True), dict(destination_id=-1),
                      dict(weight_grams=0), dict(weight_grams=True),
                      dict(couriers=[]), dict(couriers=['jne:other'])]:
            with self.subTest(extra=extra), self.assertRaises(ShippingUnavailable):
                self.request(self.good(), **extra)


if __name__ == '__main__':
    unittest.main()
