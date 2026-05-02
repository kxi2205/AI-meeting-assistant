import sys
import os
sys.path.insert(0, os.getcwd())

from utils.assignee_resolver import resolve_assignee_email

print("--- Resolver Refinement Validation ---")

# Test 1: Single prefix match
meeting1 = {
    'invitees': [
        {'name': 'snehasrijaya2005@gmail.com', 'email': 'snehasrijaya2005@gmail.com'},
        {'name': 'kartikyescity@gmail.com', 'email': 'kartikyescity@gmail.com'}
    ],
    'resolved_recipients': []
}
res1 = resolve_assignee_email("snehasrijaya2005", meeting1)
print(f"Test 1a (Exact email local part match): {res1}")

# Sneha shouldn't match snehasrijaya2005 unless the email was sneha@...
meeting1_b = {
    'invitees': [
        {'name': 'sneha@gmail.com', 'email': 'sneha@gmail.com'}
    ]
}
res1b = resolve_assignee_email("Sneha", meeting1_b)
print(f"Test 1b (Sneha -> sneha@gmail.com): {res1b}")

# Test 2: Ambiguous prefix match
meeting2 = {
    'invitees': [
        {'name': 'sneha@work.com', 'email': 'sneha@work.com'},
        {'name': 'sneha@personal.com', 'email': 'sneha@personal.com'}
    ]
}
res2 = resolve_assignee_email("Sneha", meeting2)
print(f"Test 2 (Ambiguous Sneha): {res2}")

# Test 3: Exact name match should still work and have priority
meeting3 = {
    'invitees': [
        {'name': 'Sneha Srijaya', 'email': 'sneha@example.com'}
    ]
}
res3 = resolve_assignee_email("Sneha Srijaya", meeting3)
print(f"Test 3 (Exact name match): {res3}")

# Test 4: Mismatch
res4 = resolve_assignee_email("Unknown", meeting1)
print(f"Test 4 (Unknown): {res4}")

print("--- End Validation ---")
