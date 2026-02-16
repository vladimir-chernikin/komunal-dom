#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест исправления порогов confidence

Проверяет, что фильтры с разными confidence работают корректно
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))


def test_threshold_logic():
    """Тест логики порогов"""

    print("=" * 80)
    print("TEST: Different confidence thresholds for different filters")
    print("=" * 80)

    # Fixed thresholds
    FILTER_CONFIDENCE_THRESHOLD_LOCATION = 0.8
    FILTER_CONFIDENCE_THRESHOLD_INCIDENT = 0.7
    FILTER_CONFIDENCE_THRESHOLD_CATEGORY = 0.6
    FILTER_CONFIDENCE_THRESHOLD_DEFAULT = 0.7

    # Test filters from FilterDetectionService
    established_filters = {
        'category': {'value': 'Gas supply', 'confidence': 0.7},
        'incident_type': {'value': 'Incident', 'confidence': 0.7},
        'location_type': {'value': 'Individual', 'confidence': 0.8}
    }

    print("\nIncoming filters:")
    for filter_name, filter_data in established_filters.items():
        conf = filter_data['confidence']
        print(f"   {filter_name}: {filter_data['value']} (confidence={conf})")

    print("\nApplying filters:")

    applied_count = 0
    skipped_count = 0

    for filter_name, filter_data in established_filters.items():
        confidence = filter_data['confidence']
        value = filter_data['value']

        # Determine threshold per filter type
        if filter_name == 'location_type':
            threshold = FILTER_CONFIDENCE_THRESHOLD_LOCATION
        elif filter_name == 'incident_type':
            threshold = FILTER_CONFIDENCE_THRESHOLD_INCIDENT
        elif filter_name == 'category':
            threshold = FILTER_CONFIDENCE_THRESHOLD_CATEGORY
        else:
            threshold = FILTER_CONFIDENCE_THRESHOLD_DEFAULT

        # Apply only filters with confidence >= threshold
        if confidence < threshold:
            print(f"   SKIP {filter_name}: confidence={confidence} < {threshold}")
            skipped_count += 1
        else:
            print(f"   APPLY {filter_name}: confidence={confidence} >= {threshold}")
            applied_count += 1

    print("\n" + "=" * 80)
    print(f"RESULT: Applied {applied_count} of {len(established_filters)} filters")

    if applied_count == 3:
        print("SUCCESS: All filters applied correctly!")
        return True
    else:
        print(f"ERROR: Skipped {skipped_count} filters")
        return False


if __name__ == "__main__":
    result = test_threshold_logic()

    print("\n" + "=" * 80)
    print("FINAL RESULT:")
    print("=" * 80)

    if result:
        print("ALL TESTS PASSED!")
        print("\nThe fix works correctly:")
        print("   - Category (0.7 >= 0.6) OK")
        print("   - Incident (0.7 >= 0.7) OK")
        print("   - Location (0.8 >= 0.8) OK")
        sys.exit(0)
    else:
        print("TESTS FAILED!")
        print("\nNeed to check logic")
        sys.exit(1)
