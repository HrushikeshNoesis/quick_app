# Instagram Business Login - Streamlit App

A Streamlit application that implements Instagram Business Login OAuth flow, fetches long-lived access tokens, and displays user data.

## Features

- ✅ Instagram OAuth 2.0 authentication flow
- ✅ Exchange authorization code for short-lived token
- ✅ Exchange short-lived token for long-lived token (60 days validity)
- ✅ Fetch and display user data
- ✅ Connection status indicator
- ✅ Token expiration information
- ✅ Beautiful, user-friendly interface

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Instagram App

1. Go to [Meta App Dashboard](https://developers.facebook.com/apps/)
2. Create a new app or select an existing one
3. Add the **Instagram** product to your app
4. Navigate to: **App Dashboard > Instagram > API setup with Instagram login**
5. Complete the setup steps
6. In **"Set up Instagram business login"**, configure:
   - **OAuth redirect URIs**: Add `http://localhost:8501` (or your preferred redirect URI)
   - Note your **Instagram App ID** and **Instagram App Secret**

### 3. Run the App

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

### 4. Use the App

1. Enter your **Instagram App ID** and **Instagram App Secret** in the sidebar
2. Make sure the **Redirect URI** matches what you configured in the App Dashboard
3. Click the authorization link to start the login flow
4. Grant permissions to your app
5. You'll be redirected back with your tokens and user data displayed

## How It Works

1. **Authorization**: User clicks the login link, which redirects to Instagram's OAuth page
2. **Code Exchange**: After user grants permissions, Instagram redirects back with an authorization code
3. **Short-lived Token**: The app exchanges the code for a short-lived access token (valid for 1 hour)
4. **Long-lived Token**: The app exchanges the short-lived token for a long-lived token (valid for 60 days)
5. **User Data**: The app fetches user information using the long-lived token

## Token Management

- **Short-lived token**: Valid for 1 hour, obtained immediately after authorization
- **Long-lived token**: Valid for 60 days, can be refreshed for another 60 days using the `/refresh_access_token` endpoint
- Tokens are stored in Streamlit session state (cleared when you refresh the page)

## API Endpoints Used

- `https://www.instagram.com/oauth/authorize` - Authorization
- `https://api.instagram.com/oauth/access_token` - Exchange code for short-lived token
- `https://graph.instagram.com/access_token` - Exchange for long-lived token
- `https://graph.instagram.com/refresh_access_token` - Refresh long-lived token
- `https://graph.instagram.com/me` - Get user data

## Requirements

- Python 3.7+
- Streamlit 1.28.0+
- Requests 2.31.0+
- Instagram Business Account
- Meta App with Instagram product configured

## Notes

- The app secret should never be exposed in client-side code
- Long-lived token exchange must be done server-side (which Streamlit handles)
- Make sure your redirect URI exactly matches what's configured in the App Dashboard
- The authorization code is valid for 1 hour and can only be used once

## Troubleshooting

- **"Matching code was not found"**: The authorization code may have expired or been used already
- **Redirect URI mismatch**: Ensure the redirect URI in the app matches exactly with the App Dashboard
- **Invalid credentials**: Double-check your App ID and App Secret
- **Access denied**: User may have denied permissions or the app doesn't have the required access level

