import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import os
from pymongo import MongoClient
import dateparser
from datetime import datetime

def get_external_ip():
    response = requests.get("https://api.ipify.org?format=json")
    if response.status_code == 200:
        data = response.json()
        return data.get("ip")
    else:
        return "Unknown"

external_ip = get_external_ip()
print("External IP:", external_ip)

# Get the URL
url = os.environ.get('URL')

# Use the URL
k = requests.get(url).text

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36'}
soup=BeautifulSoup(k,'html.parser')
# Find all div tags with class gridrow
gridrows = soup.find_all('div', class_='gridrow')

event_datum = None
found_event = False

# Store the data in a database
client = MongoClient(os.environ.get('DB_URL'))
db = client['eventDb']
collection = db['EventDetails']

# For each gridrow
for gridrow in gridrows:
    # a gridrow contains eather a date or an event-thema or the time, the seats and the link_div to the event
    # if it contains a date, the date is stored in the variable current_date
    # if it contains an event-thema, it has to be checked if it is the event we are looking for
    # if it contains the event we are looking for, we can check the next gridrow for the time, the seats and the link_div to the event

    # store the date of the event
    current_date = gridrow.find('div', class_='gridcolumn small-12 large-12 event-datum')

    # if there is a date, goto the next gridrow
    if current_date is not None: 
        event_datum = current_date
        continue

    # check if there is an event-thema
    if found_event is False:
        event = gridrow.find('div', class_='event-thema')

    # if there is an event-thema, check if it is the event we are looking for
    if found_event is False and event is not None:
        # check if the event-thema is the event we are looking for
        if event.text.strip() == 'Figurentheater Petruschka öffentlich':
            # if it is the event we are looking for, goto the next gridrow
            found_event = True
            continue
        else:
            # if it is not the event we are looking for, goto the next gridrow
            # reset the current_date and found_event
            #  event_datum = None
            found_event = False
            continue
    # if there is no date and no event-thema, goto the next gridrow
    if event is None:
        continue

    # if there is no date and no event-thema, check if it is the time, the seats and the link_div to the event
    event_time = gridrow.find('div', class_='gridcolumn small-2 large-1')  # This is the time element
    seats_div = gridrow.find('div', class_='gridcolumn-last')
    link_div = gridrow.find('a', href=True)

    if event_time is not None and seats_div is not None and link_div is not None:

        # This is a day row, store the date and time and reset found_event
        event_datum_text = event_datum.text.strip()

        # reset the event_datum and found_event
        event_datum = None
        found_event = False

        # Find the seats information
        seats_text = seats_div.text.strip()
        if seats_text == 'Ausgebucht':
            seats_text = '0'
        else:
            # Find all digits in the string
            seats_text = int(''.join(re.findall(r'\d', seats_text))).__str__()

        link_text = link_div['href']

        event_datum_text = event_datum_text + ' ' + event_time.text.strip()
        # Parse the date and time string
        current_date = dateparser.parse(event_datum_text)

        # Create a datetime object with the date and time you want to search for
        search_datestart = datetime(current_date.year, current_date.month, current_date.day, current_date.hour-4, current_date.minute)
        search_dateend = datetime(current_date.year, current_date.month, current_date.day, current_date.hour+4, current_date.minute)

        # Store the data in the database
        # Use the datetime object to find a record
        record = collection.find_one({'start': {'$lt': search_dateend, '$gte': search_datestart}})
        if record is not None:

            # Check if there is a link on each element of the records eventInfo - array
            # loop through the eventInfo array
            for eventInfo in record['eventInfos']:
                # if there is a link in the eventInfo array, store the link in the variable link
                if 'url' in eventInfo:
                    link = eventInfo['url']
                else:
                    link = None

                # if the link is the same as the link_text, do nothing
                if link == link_text:
                    break
                else:
                    # if the link is different, update the link in the database
                    result = collection.update_one(
                        {'start': {'$lt': search_dateend, '$gte': search_datestart}, 'eventInfos.url': 'https://naturmuseum.lu.ch/veranstaltungen/anmeldung?id=xxx&account=nml'},
                        {'$set': {'eventInfos.$.url': link_text}}
)
            # The event is already in the database
            # Check if the seats information is different
            if collection.find_one({'start': {'$lt': search_dateend, '$gte': search_datestart}, 'saleState': seats_text}):
                # The seats information is the same, do nothing
                # print the date in the same format as the database
                print ('Event unchanged: ' + search_datestart.strftime('%Y-%m-%d %H:%M'))
                pass
            else:
                # The seats information is different, update the database
                result = collection.update_one({'start': {'$lt': search_dateend, '$gte': search_datestart}}, {'$set': {'saleState': seats_text}})                    
                print('Updated event: ' + search_datestart.strftime('%Y-%m-%d %H:%M'))
        else:
            print('Event not found: ' + search_datestart.strftime('%Y-%m-%d %H:%M'))
            pass
