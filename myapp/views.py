from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from myapp.auth_helper import get_sign_in_flow, get_token_from_code, store_user, remove_user_and_token, get_token
from myapp.graph_helper import *
from .models import Event
import json
import os
from django.utils import timezone
import pytz
from datetime import datetime


def home(request):
    context = initialize_context(request)

    # Check if the access_token.json file exists
    if os.path.exists('access_token.json'):
        # Load the access token from the JSON file
        with open('access_token.json', 'r') as f:
            token_data = json.load(f)

        # Check if the access token exists
        if 'access_token' in token_data:
            token = token_data['access_token']

            headers = {
                'Authorization': 'Bearer ' + token,
            }

            # List all events
            response = requests.get(
                graph_url + '/me/events',
                headers=headers,
            )

            # Write all events to a JSON file
            events = response.json().get('value', [])
            with open('events.json', 'w') as f:
                json.dump(events, f, indent=4)

           # Save the events to the database
            for event in events:
                # Parse the start and end times as naive datetime objects
                start_time_naive = parse_datetime(event['start']['dateTime'])
                end_time_naive = parse_datetime(event['end']['dateTime'])

                # Make the datetime objects aware
                ist = pytz.timezone('Asia/Kolkata')
                start_time = ist.localize(start_time_naive)
                end_time = ist.localize(end_time_naive)
                
                # Get the location, attendees, and description
                location = event['location']['displayName']
                attendees = json.dumps(event['attendees'])  # Convert the attendees list to a JSON string
                description = event['bodyPreview']

                # Get the additional fields
                is_cancelled = event['isCancelled']
                is_online_meeting = event['isOnlineMeeting']
                online_meeting_provider = event['onlineMeetingProvider']
                web_link = event['webLink']

                # Check if the event already exists in the database
                if not Event.objects.filter(subject=event['subject'], start_time=start_time, end_time=end_time).exists():
                    # Create a new Event object
                    Event.objects.create(
                        subject=event['subject'],
                        start_time=start_time,
                        end_time=end_time,
                        location=location,
                        attendees=attendees,
                        description=description,
                        is_cancelled=is_cancelled,
                        is_online_meeting=is_online_meeting,
                        online_meeting_provider=online_meeting_provider,
                        web_link=web_link,
                        # Add any other fields you need
                    )
            events = Event.objects.all()

            # Create a new list to store the modified events
            modified_events = []
            for event in events:
                # Parse attendees JSON into list of dictionaries
                attendees_data = json.loads(event.attendees)
                
                # Extract email addresses from attendees data
                email_addresses = [attendee['emailAddress']['address'] for attendee in attendees_data]
                
                # Modify the event's attendees attribute in-place
                event.attendees = ', '.join(email_addresses)

                # Add the modified event to the new list
                modified_events.append(event)

            # Get the date from the GET parameters
            date = request.GET.get('date')

            # If a date was provided, filter the events by this date
            if date:
                date = datetime.strptime(date, '%Y-%m-%d').date()  # Convert the string to a date object
                events = Event.objects.filter(start_time__date=date)

            context['events'] = modified_events

    return render(request, 'myapp/home.html', context)

def initialize_context(request):
    context = {}
    error = request.session.pop('flash_error', None)
    if error is not None:
        context['errors'] = []
        context['errors'].append(error)
    # Check for user in the session
    context['user'] = request.session.get('user', {'is_authenticated': False})
    return context

def sign_in(request):
    # Get the sign-in flow
    flow = get_sign_in_flow()
    # Save the expected flow so we can use it in the callback
    try:
        request.session['auth_flow'] = flow
    except Exception as e:
        print(e)
    # Redirect to the Azure sign-in page
    return HttpResponseRedirect(flow['auth_uri'])

def sign_out(request):
    # Clear out the user and token
    remove_user_and_token(request)

    # Delete the access_token.json file
    if os.path.exists('access_token.json'):
        os.remove('access_token.json')

    # Delete the events.json file
    if os.path.exists('events.json'):
        os.remove('events.json')

    # Clear the session
    request.session.clear()

    # Delete all events
    Event.objects.all().delete()

    return HttpResponseRedirect(reverse('home'))

def callback(request):
    # Make the token request
    result = get_token_from_code(request)

    # Save the token to a JSON file
    with open('access_token.json', 'w') as f:
        json.dump(result, f)

    # Get the user's profile
    user = get_user(result['access_token'])

    # Store user
    store_user(request, user)

    return HttpResponseRedirect(reverse('home'))

