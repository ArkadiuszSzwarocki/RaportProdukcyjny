from app.core.factory import create_app

app = create_app()

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['pracownik_id'] = 1
        sess['rola'] = 'lider'
    
    # Fetch the wnioski panel
    resp = client.get('/panel_wnioski_page?fragment=true', headers={
        'X-Requested-With': 'XMLHttpRequest'
    })
    
    print(f"Status: {resp.status_code}")
    html_response = resp.get_data(as_text=True)
    
    # Check if the response contains wnioski
    if 'wnioski' in html_response.lower():
        print("✓ Response contains 'wnioski'")
    else:
        print("✗ Response does NOT contain 'wnioski'")
    
    # Show first 1000 chars
    print("\nFirst 1000 chars of response:")
    print(html_response[:1000])
