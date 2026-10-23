"""Read approved meal coverage exports without guessing fees or meal access."""
import csv
import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

HEADER = ['Pincode', 'Area', 'Breakfast', 'Lunch', 'Dinner', 'Snacks',
          'Delivery Charge (₹)', 'Min Order (₹)', 'Active']


def read_meal_zone_csv(source):
    reader = csv.reader(source)
    for row in reader:
        cells = [cell.strip().lstrip('\ufeff') for cell in row]
        if cells and cells[0] == 'Pincode':
            if cells != HEADER:
                raise ValidationError('The delivery CSV columns do not match the meal-zone export.')
            break
    else:
        raise ValidationError('The delivery CSV has no Pincode header.')

    def flag(value):
        if value.lower() not in ('yes', 'no'):
            raise ValueError
        return value.lower() == 'yes'

    def amount(value, maximum):
        result = Decimal(value.replace('₹', '').replace(',', '').strip())
        if not result.is_finite() or not 0 <= result <= maximum or result.as_tuple().exponent < -2:
            raise ValueError
        return result

    result, seen = [], set()
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        try:
            if len(row) != len(HEADER):
                raise ValueError
            pin, area, breakfast, lunch, dinner, snacks, fee, minimum, active = [cell.strip() for cell in row]
            if not re.fullmatch(r'[1-9][0-9]{5}', pin):
                raise ValueError
            area = '' if area in ('', '—', '-') else area
            if len(area) > 120 or (pin, area.casefold()) in seen:
                raise ValueError
            slots = [key for key, value in zip(('breakfast', 'lunch', 'dinner', 'snacks'),
                                               (breakfast, lunch, dinner, snacks)) if flag(value)]
            enabled = flag(active)
            if enabled and not slots:
                raise ValueError  # An empty slot list means all meals in the model.
            values = {'pincode': pin, 'area_name': area,
                      'delivery_fee': amount(fee, Decimal('99999.99')),
                      'min_order': amount(minimum, Decimal('999999.99')),
                      'slot_keys': slots, 'active': enabled}
        except (ValueError, InvalidOperation):
            raise ValidationError(f'Invalid or duplicate meal delivery zone on CSV line {reader.line_num}.')
        seen.add((pin, area.casefold()))
        result.append(values)
    if not result:
        raise ValidationError('The meal delivery CSV has no zones.')
    return result
