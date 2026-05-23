import requests

def test_live_login():
    session = requests.Session()
    login_url = "http://127.0.0.1:8082/login"
    
    print("Sending POST request to /login as GrysDawi...")
    response = session.post(login_url, data={
        "login": "GrysDawi",
        "haslo": "haslo123"
    }, allow_redirects=False)
    
    print(f"Status Code: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    
    if "Location" in response.headers:
        redirect_target = response.headers["Location"]
        if redirect_target.startswith("/"):
            redirect_target = "http://127.0.0.1:8082" + redirect_target
        print(f"Redirect Target: {redirect_target}")
        
        # Now follow the redirect and inspect headers
        print("\nFollowing redirect to target page...")
        follow_response = session.get(redirect_target, allow_redirects=False)
        print(f"Followed Page Status Code: {follow_response.status_code}")
        print("Followed Page Caching Headers:")
        print(f"  Cache-Control: {follow_response.headers.get('Cache-Control')}")
        print(f"  Pragma: {follow_response.headers.get('Pragma')}")
        print(f"  Expires: {follow_response.headers.get('Expires')}")
        
        # Verify correctness
        expected_redirect_part = "sekcja=Zasyp"
        if expected_redirect_part in redirect_target:
            print("\n[SUCCESS] Redirected to the correct first allowed section!")
        else:
            print(f"\n[FAILURE] Did not redirect to an allowed section. Target: {redirect_target}")
            
        cache_control = follow_response.headers.get('Cache-Control', '')
        if 'no-store' in cache_control and 'no-cache' in cache_control:
            print("[SUCCESS] Caching headers are correctly set to disable BFCache!")
        else:
            print(f"\n[FAILURE] Cache headers do not disable caching: {cache_control}")
    else:
        print("\n[FAILURE] No redirect location header found in login response!")

if __name__ == "__main__":
    test_live_login()
