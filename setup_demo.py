"""
Setup script to initialize demo user and test data.
Run this once to set up the demo account.
"""

from database import init_database, register_user
from auth import validate_email, validate_password_strength, validate_username

def setup_demo():
    """Create demo user account."""
    print("Initializing database...")
    init_database()
    
    demo_user = "demo"
    demo_email = "demo@example.com"
    demo_password = "Demo1234"
    
    print(f"\nSetting up demo account...")
    print(f"Username: {demo_user}")
    print(f"Email: {demo_email}")
    print(f"Password: {demo_password}")
    
    # Validate inputs
    valid_user, msg = validate_username(demo_user)
    if not valid_user:
        print(f"❌ Username validation failed: {msg}")
        return
    
    valid_email = validate_email(demo_email)
    if not valid_email:
        print(f"❌ Email validation failed")
        return
    
    valid_pwd, msg = validate_password_strength(demo_password)
    if not valid_pwd:
        print(f"❌ Password validation failed: {msg}")
        return
    
    # Register user
    success, message = register_user(demo_user, demo_email, demo_password)
    if success:
        print(f"✅ {message}")
    else:
        print(f"ℹ️  {message}")

if __name__ == "__main__":
    setup_demo()
    print("\n✨ Setup complete! You can now login with the demo account.")
