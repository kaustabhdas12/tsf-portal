import yaml
import msal
import os
import json

# Load the oauth_settings.yml file located in your app DIR
# Get the directory of the current file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the full path to the oauth_settings.yml file
settings_file = os.path.join(current_dir, '..', 'oauth_settings.yml')

# Open the file
with open(settings_file, 'r') as stream:
    settings = yaml.safe_load(stream)

def load_cache(request):
  # Check for a token cache in the session
  cache = msal.SerializableTokenCache()
  if request.session.get('token_cache'):
    cache.deserialize(request.session['token_cache'])
  return cache

def save_cache(request, cache):
  # If cache has changed, persist back to session
  if cache.has_state_changed:
    request.session['token_cache'] = cache.serialize()

def get_msal_app(cache=None):
  # Initialize the MSAL confidential client
  auth_app = msal.ConfidentialClientApplication(
    settings['app_id'],
    authority=settings['authority'],
    client_credential=settings['app_secret'],
    token_cache=cache)
  return auth_app

# Method to generate a sign-in flow
def get_sign_in_flow():
  auth_app = get_msal_app()
  return auth_app.initiate_auth_code_flow(
    settings['scopes'],
    redirect_uri=settings['redirect'])

# Method to exchange auth code for access token
def get_token_from_code(request):
  cache = load_cache(request)
  auth_app = get_msal_app(cache)

  # Get the flow saved in session
  flow = request.session.pop('auth_flow', {})
  result = auth_app.acquire_token_by_auth_code_flow(flow, request.GET)
  save_cache(request, cache)

  return result


def store_user(request, user):
  try:
    request.session['user'] = {
      'is_authenticated': True,
      'name': user['displayName'],
      'email': user['mail'] if (user['mail'] != None) else user['userPrincipalName'],
      'timeZone': user['mailboxSettings']['timeZone'] if (user['mailboxSettings']['timeZone'] != None) else 'UTC'
    }
  except Exception as e:
    print(e)

def get_token(request):
    cache = load_cache(request)
    auth_app = get_msal_app(cache)

    accounts = auth_app.get_accounts()
    if accounts:
        # First, try to get the token silently
        result = auth_app.acquire_token_silent(
            settings['scopes'],
            account=accounts[0]
        )

        # If acquire_token_silent didn't work, then get a new token using a refresh token
        if 'error' in result and result['error'] == 'invalid_grant':
            # Open the access_token.json file
            with open('access_token.json', 'r') as f:
                token_data = json.load(f)

            # Get the refresh token
            refresh_token = token_data['refresh_token']

            # Now use the refresh token to get a new access token
            result = auth_app.acquire_token_by_refresh_token(refresh_token, settings['scopes'])

        save_cache(request, cache)

        return result['access_token']


def remove_user_and_token(request):
  if 'token_cache' in request.session:
    del request.session['token_cache']

  if 'user' in request.session:
    del request.session['user']