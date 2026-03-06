import sys
import os

# Add project root to path
sys.path.append(r'd:\AI Voice Guardian')

from distress_detection import analyze_speech

def test_detection():
    test_cases = [
        {"text": "SOS help me", "expected_status": "EMERGENCY", "desc": "Direct SOS keyword"},
        {"text": "I am in danger", "expected_status": "EMERGENCY", "desc": "Danger keyword"},
        {"text": "Hello how are you", "expected_status": "NORMAL", "desc": "Normal conversation"},
        {"text": "I am feeling very scared and threatened right now", "expected_status": "EMERGENCY", "desc": "High threat score (sentiment + keywords)"},
        {"text": "", "expected_status": "NORMAL", "desc": "Empty input"}
    ]

    print("Running Detection Logic Verification...\n")
    all_passed = True
    for case in test_cases:
        result = analyze_speech(case['text'])
        passed = result['alert_status'] == case['expected_status']
        print(f"[{'PASS' if passed else 'FAIL'}] {case['desc']}")
        print(f"  Input: '{case['text']}'")
        print(f"  Result: {result}\n")
        if not passed:
            all_passed = False

    if all_passed:
        print("All verification tests PASSED!")
    else:
        print("Some tests FAILED.")

if __name__ == "__main__":
    test_detection()
