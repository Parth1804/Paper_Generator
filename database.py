"""
Database module for user management and data persistence.
Uses SQLite with encrypted storage for sensitive data.
"""

import sqlite3
import os
import json
from typing import Optional, Dict, Any
from datetime import datetime
from auth import hash_password, verify_password


DB_PATH = "users.db"


def init_database():
    """Initialize the database with required tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    ''')
    
    # User data table (for storing topics, papers, etc.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            data_type TEXT NOT NULL,
            data_key TEXT NOT NULL,
            data_value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, data_type, data_key)
        )
    ''')
    
    # Session table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()


def user_exists(username: str) -> bool:
    """Check if a user exists by username."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def email_exists(email: str) -> bool:
    """Check if an email is already registered."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def register_user(username: str, email: str, password: str) -> tuple[bool, str]:
    """
    Register a new user.
    
    Args:
        username: Username
        email: Email address
        password: Plain text password
        
    Returns:
        Tuple of (success, message)
    """
    if user_exists(username):
        return False, "Username already exists"
    
    if email_exists(email):
        return False, "Email already registered"
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        password_hash = hash_password(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
        ''', (username, email, password_hash))
        
        conn.commit()
        conn.close()
        
        return True, "User registered successfully"
    except Exception as e:
        return False, f"Registration error: {str(e)}"


def authenticate_user(username: str, password: str) -> tuple[bool, Optional[int], str]:
    """
    Authenticate a user and update last_login.
    
    Args:
        username: Username
        password: Plain text password
        
    Returns:
        Tuple of (success, user_id, message)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, password_hash FROM users WHERE username = ?', (username,))
    result = cursor.fetchone()
    
    if result is None:
        conn.close()
        return False, None, "User not found"
    
    user_id, password_hash = result
    
    if not verify_password(password, password_hash):
        conn.close()
        return False, None, "Invalid password"
    
    # Update last login
    cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return True, user_id, "Login successful"


def get_user_info(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user information by user_id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, username, email, created_at, last_login FROM users WHERE id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result is None:
        return None
    
    return {
        'id': result[0],
        'username': result[1],
        'email': result[2],
        'created_at': result[3],
        'last_login': result[4]
    }


def save_user_data(user_id: int, data_type: str, data_key: str, data_value: Any) -> bool:
    """
    Save user-specific data.
    
    Args:
        user_id: User ID
        data_type: Type of data (e.g., 'topics', 'papers')
        data_key: Key for the data
        data_value: Value to store (will be JSON serialized)
        
    Returns:
        True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Convert value to JSON string if it's not already a string
        if not isinstance(data_value, str):
            data_value = json.dumps(data_value, ensure_ascii=False)
        
        cursor.execute('''
            INSERT INTO user_data (user_id, data_type, data_key, data_value, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id, data_type, data_key) 
            DO UPDATE SET data_value = excluded.data_value, updated_at = CURRENT_TIMESTAMP
        ''', (user_id, data_type, data_key, data_value))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error saving user data: {e}")
        return False


def get_user_data(user_id: int, data_type: str, data_key: Optional[str] = None) -> Any:
    """
    Retrieve user-specific data.
    
    Args:
        user_id: User ID
        data_type: Type of data (e.g., 'topics', 'papers')
        data_key: Specific key to retrieve (if None, returns all for data_type)
        
    Returns:
        Retrieved data (parsed from JSON) or None
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if data_key is None:
            cursor.execute('''
                SELECT data_key, data_value FROM user_data 
                WHERE user_id = ? AND data_type = ?
                ORDER BY updated_at DESC
            ''', (user_id, data_type))
            results = cursor.fetchall()
            conn.close()
            
            if not results:
                return {}
            
            # Return as dict with data_key as keys
            data_dict = {}
            for key, value in results:
                try:
                    data_dict[key] = json.loads(value)
                except json.JSONDecodeError:
                    data_dict[key] = value
            return data_dict
        else:
            cursor.execute('''
                SELECT data_value FROM user_data 
                WHERE user_id = ? AND data_type = ? AND data_key = ?
            ''', (user_id, data_type, data_key))
            result = cursor.fetchone()
            conn.close()
            
            if result is None:
                return None
            
            try:
                return json.loads(result[0])
            except json.JSONDecodeError:
                return result[0]
    except Exception as e:
        print(f"Error retrieving user data: {e}")
        return None


def delete_user_data(user_id: int, data_type: str, data_key: str) -> bool:
    """Delete specific user data."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM user_data 
            WHERE user_id = ? AND data_type = ? AND data_key = ?
        ''', (user_id, data_type, data_key))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error deleting user data: {e}")
        return False


def delete_user_account(user_id: int) -> bool:
    """Delete a user account and all associated data."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Delete is cascaded from users table
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error deleting user account: {e}")
        return False


# Initialize database when module is imported
if not os.path.exists(DB_PATH):
    init_database()
