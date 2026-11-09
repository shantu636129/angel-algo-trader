import pyotp
from SmartApi import SmartConnect
from config import settings
from utils.rate_limiter import rate_limited

class AngelAuth:
    def __init__(self):
        self.smart_api = SmartConnect(api_key=settings.API_KEY)
        self.jwt_token = None
        self.refresh_token = None
        self.feed_token = None

    @rate_limited("login")  # 1 req/sec
    def login(self):
        """Generates a new login session using TOTP."""
        try:
            totp_code = pyotp.TOTP(settings.TOTP_SECRET).now()
            session = self.smart_api.generateSession(
                settings.CLIENT_CODE, 
                settings.PIN, 
                totp_code
            )

            if session.get('status'):
                self.jwt_token = session['data']['jwtToken']
                self.refresh_token = session['data']['refreshToken']
                self.feed_token = self.smart_api.getfeedToken()
                print("[AUTH] ✅ Login Successful!")
                return True
            else:
                print(f"[AUTH] ❌ Login Failed: {session.get('message')}")
                return False

        except Exception as e:
            print(f"[AUTH] ❌ Exception during login: {e}")
            return False

    @rate_limited("get_profile")  # 3 req/sec, 1000/hr
    def get_user_profile(self):
        """Fetches profile details of the logged-in user."""
        if not self.refresh_token:
            print("[AUTH] ⚠️ No active session found. Please log in first.")
            return None

        try:
            profile = self.smart_api.getProfile(self.refresh_token)
            if profile.get('status'):
                return profile.get('data')
            else:
                print(f"[AUTH] ❌ Failed to fetch profile: {profile.get('message')}")
                return None
        except Exception as e:
            print(f"[AUTH] ❌ Error fetching profile: {e}")
            return None

    @rate_limited("logout")  # 1 req/sec
    def logout_session(self):
        """Logs out and invalidates the session token."""
        try:
            response = self.smart_api.terminateSession(settings.CLIENT_CODE)
            if response.get('status'):
                print("[AUTH] ✅ Session Terminated Successfully.")
                return True
            else:
                print(f"[AUTH] ❌ Logout failed: {response.get('message')}")
                return False
        except Exception as e:
            print(f"[AUTH] ❌ Error during logout: {e}")
            return False
