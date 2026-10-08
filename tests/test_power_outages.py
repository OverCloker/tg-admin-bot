import unittest
from datetime import date
from app.power_outages import parse_schedule, valid_location


class PowerScheduleTests(unittest.TestCase):
    day = date(2026, 10, 8)

    def html(self, slots):
        return '<title>Світло 08.10.2026</title>' + ''.join(
            f'<div class="bz-schedule-slot bz-schedule-slot--{state}">'
            f'<span class="bz-schedule-slot__time">{start} – {end}</span></div>'
            for start, end, state in slots)

    def test_full_day_and_midnight(self):
        result = parse_schedule(self.html([('00:00', '12:30', 'on'), ('12:30', '24:00', 'off')]), self.day)
        self.assertEqual(result, [{'start': 0, 'end': 750, 'status': 'on'}, {'start': 750, 'end': 1440, 'status': 'off'}])

    def test_gap_overlap_and_bad_clock_rejected(self):
        for slots in [ [('00:00', '12:00', 'on'), ('12:30', '24:00', 'off')],
                       [('00:00', '13:00', 'on'), ('12:30', '24:00', 'off')],
                       [('00:00', '24:30', 'on')] ]:
            self.assertEqual(parse_schedule(self.html(slots), self.day), [])

    def test_other_day_not_reused(self):
        self.assertEqual(parse_schedule(self.html([('00:00', '24:00', 'on')]), date(2026, 10, 9)), [])

    def test_unknown_is_not_light_on(self):
        self.assertEqual(parse_schedule(self.html([('00:00', '24:00', 'maybe')]), self.day)[0]['status'], 'unknown')

    def test_location_validation(self):
        self.assertTrue(valid_location('/poltavska-oblast/cutivska-hromada/cutove'))
        for path in ['https://example.com', '/poltavska-oblast/../secret', '/poltavska-oblast/cherha-1-1', '/kyiv/kyiv']:
            self.assertFalse(valid_location(path))
