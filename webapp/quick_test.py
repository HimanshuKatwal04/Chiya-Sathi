#!/usr/bin/env python3
"""
Quick test of critical fixes
"""
import asyncio
import httpx
import json

BASE_URL = "http://localhost:8501"

# Test critical cases that failed
TEST_CASES = [
    {"id": 3, "symptoms": "shooting pain in chest since morning", "age": "45", "sex": "male", "expected": "YELLOW", "description": "Shooting pain → cardiac, not gunshot"},
    {"id": 52, "symptoms": "pain in right lower abdomen since yesterday, worse when I walk, mild fever", "age": "19", "sex": "female", "expected": "RED", "description": "Appendicitis"},
    {"id": 66, "symptoms": "pesticide sprayed on hands and face 2 hours ago, nausea, dizziness, excessive saliva", "age": "35", "sex": "male", "expected": "RED", "description": "Pesticide exposure"},
]

async def test_case(client, case):
    try:
        data = {
            "symptoms": case["symptoms"],
            "age": case["age"],
            "sex": case["sex"],
            "language": "en"
        }
        resp = await client.post(f"{BASE_URL}/triage", data=data, timeout=60)
        result = resp.json()
        got = result.get("triage_level", "UNKNOWN")
        correct = got == case["expected"]
        
        print(f"Case {case['id']}: {case['description']}")
        print(f"  Expected: {case['expected']}, Got: {got} {'✅' if correct else '❌'}")
        if result.get("referral_reason"):
            print(f"  Reason: {result['referral_reason']}")
        print()
        
        return correct
    except Exception as e:
        print(f"Case {case['id']}: ERROR - {e}")
        return False

async def main():
    print("Testing critical fixes...")
    print("=" * 50)
    
    results = []
    async with httpx.AsyncClient() as client:
        for case in TEST_CASES:
            correct = await test_case(client, case)
            results.append(correct)
    
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} ({passed/total*100:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())